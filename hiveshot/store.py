"""SQLite persistence (stdlib sqlite3, WAL) for sessions, shots and tips."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Optional, Union

from .models import (
    BallType,
    DragFit,
    ParabolaFit,
    Point3D,
    Shot,
    ShotResult,
    TipEvent,
    Track3D,
)

IPS_TO_MPS = 0.0254

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY, name TEXT NOT NULL,
  started_at REAL NOT NULL, ended_at REAL);
CREATE TABLE IF NOT EXISTS shots (
  shot_id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
  t_launch REAL, burst_id INTEGER, burst_index INTEGER, ball_type TEXT, result TEXT,
  exit_speed_ips REAL, launch_angle_deg REAL, launch_azimuth_deg REAL,
  apex_z_in REAL, launch_point TEXT, parabola TEXT, drag TEXT, track TEXT,
  clip_path TEXT, notes TEXT, created_at REAL);
CREATE INDEX IF NOT EXISTS idx_shots_session ON shots(session_id);
CREATE TABLE IF NOT EXISTS tips (
  tip_id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, t REAL,
  alliance TEXT, new_up_cell TEXT, caused_by_shot_id INTEGER);
CREATE INDEX IF NOT EXISTS idx_tips_session ON tips(session_id);
CREATE TABLE IF NOT EXISTS calibration (
  name TEXT PRIMARY KEY, blob TEXT NOT NULL, updated_at REAL);
"""


def _dumps(o) -> Optional[str]:
    return None if o is None else json.dumps(o)


def _loads(s):
    return None if s is None else json.loads(s)


class Store:
    def __init__(self, path: Union[str, Path]):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._closed = False
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        if self.path != ":memory:":
            self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        with self._lock:
            self._db.executescript(SCHEMA)
            self._db.commit()

    def close(self) -> None:
        """Close the database (idempotent). Callers must stop the pipeline first."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._db.close()

    def ensure_session(self, session_id: str, name: str) -> None:
        """Create a fixed-id session if missing; it is created already ended so it never
        counts as the open/current session."""
        with self._lock:
            now = time.time()
            self._db.execute("INSERT OR IGNORE INTO sessions VALUES (?,?,?,?)",
                             (session_id, name, now, now))
            self._db.commit()

    # -- sessions ----------------------------------------------------------
    def create_session(self, name: str) -> str:
        sid = uuid.uuid4().hex[:8]
        with self._lock:
            self._db.execute("INSERT INTO sessions VALUES (?,?,?,NULL)", (sid, name, time.time()))
            self._db.commit()
        return sid

    def end_session(self, session_id: str) -> bool:
        with self._lock:
            cur = self._db.execute(
                "UPDATE sessions SET ended_at=? WHERE session_id=? AND ended_at IS NULL",
                (time.time(), session_id))
            self._db.commit()
            return cur.rowcount > 0

    def session_exists(self, session_id: str) -> bool:
        with self._lock:
            r = self._db.execute("SELECT 1 FROM sessions WHERE session_id=?",
                                 (session_id,)).fetchone()
        return r is not None

    def list_sessions(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT s.session_id, s.name, s.started_at, s.ended_at,"
                " COUNT(h.shot_id) AS shots,"
                " COALESCE(SUM(h.result='made'),0) AS made"
                " FROM sessions s LEFT JOIN shots h ON h.session_id=s.session_id"
                " GROUP BY s.session_id ORDER BY s.started_at, s.rowid").fetchall()
        return [dict(r) for r in rows]

    def session_summary(self, session_id: str) -> Optional[dict]:
        for s in self.list_sessions():
            if s["session_id"] == session_id:
                return s
        return None

    def open_sessions(self) -> list[str]:
        with self._lock:
            return [r[0] for r in self._db.execute(
                "SELECT session_id FROM sessions WHERE ended_at IS NULL")]

    # -- shots -------------------------------------------------------------
    def add_shot(self, shot: Shot) -> Shot:
        """Insert; a new unique shot_id is always assigned. Returns the stored Shot."""
        tr = shot.track
        track_j = None if tr is None else {
            "track_id": tr.track_id, "ball_type": tr.ball_type.value,
            "points": [[p.t, p.x, p.y, p.z, p.residual_in] for p in tr.points]}
        par = None if shot.parabola is None else vars(shot.parabola)
        drag = None if shot.drag is None else {
            "v0": list(shot.drag.v0), "p0": list(shot.drag.p0),
            "k_per_in": shot.drag.k_per_in, "rmse_in": shot.drag.rmse_in}
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO shots (session_id,t_launch,burst_id,burst_index,ball_type,result,"
                "exit_speed_ips,launch_angle_deg,launch_azimuth_deg,apex_z_in,launch_point,"
                "parabola,drag,track,clip_path,notes,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (shot.session_id, shot.t_launch, shot.burst_id, shot.burst_index,
                 shot.ball_type.value, shot.result.value, shot.exit_speed_ips,
                 shot.launch_angle_deg, shot.launch_azimuth_deg, shot.apex_z_in,
                 _dumps(None if shot.launch_point is None else list(shot.launch_point)),
                 _dumps(par), _dumps(drag), _dumps(track_j), shot.clip_path, shot.notes,
                 time.time()))
            self._db.commit()
            return replace(shot, shot_id=int(cur.lastrowid))

    def update_burst(self, shot_id: int, burst_id: int, burst_index: int, notes: str) -> None:
        with self._lock:
            self._db.execute("UPDATE shots SET burst_id=?, burst_index=?, notes=? WHERE shot_id=?",
                             (burst_id, burst_index, notes, shot_id))
            self._db.commit()

    def set_clip_path(self, shot_id: int, clip_path: Optional[str]) -> None:
        with self._lock:
            self._db.execute("UPDATE shots SET clip_path=? WHERE shot_id=?", (clip_path, shot_id))
            self._db.commit()

    @staticmethod
    def _row_to_shot(r: sqlite3.Row) -> Shot:
        tj = _loads(r["track"])
        track = None
        if tj is not None:
            track = Track3D(track_id=tj["track_id"], ball_type=BallType(tj["ball_type"]),
                            points=[Point3D(*p) for p in tj["points"]])
        par = _loads(r["parabola"])
        drag = _loads(r["drag"])
        lp = _loads(r["launch_point"])
        return Shot(
            shot_id=r["shot_id"], session_id=r["session_id"], t_launch=r["t_launch"],
            burst_id=r["burst_id"], burst_index=r["burst_index"],
            ball_type=BallType(r["ball_type"]), result=ShotResult(r["result"]),
            exit_speed_ips=r["exit_speed_ips"], launch_angle_deg=r["launch_angle_deg"],
            launch_azimuth_deg=r["launch_azimuth_deg"],
            launch_point=None if lp is None else tuple(lp), apex_z_in=r["apex_z_in"],
            parabola=None if par is None else ParabolaFit(**par),
            drag=None if drag is None else DragFit(
                v0=tuple(drag["v0"]), p0=tuple(drag["p0"]),
                k_per_in=drag["k_per_in"], rmse_in=drag["rmse_in"]),
            track=track, clip_path=r["clip_path"], notes=r["notes"] or "")

    def list_shots(self, session_id: str) -> list[Shot]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM shots WHERE session_id=? ORDER BY t_launch, shot_id",
                (session_id,)).fetchall()
        return [self._row_to_shot(r) for r in rows]

    def get_shot(self, shot_id: int) -> Optional[Shot]:
        with self._lock:
            r = self._db.execute("SELECT * FROM shots WHERE shot_id=?", (shot_id,)).fetchone()
        return None if r is None else self._row_to_shot(r)

    # -- tips --------------------------------------------------------------
    def add_tip(self, tip: TipEvent) -> int:
        """Insert a tip; returns its tip_id (used to link it to a shot later)."""
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO tips (session_id,t,alliance,new_up_cell,caused_by_shot_id)"
                " VALUES (?,?,?,?,?)",
                (tip.session_id, tip.t, tip.alliance, tip.new_up_cell, tip.caused_by_shot_id))
            self._db.commit()
            return int(cur.lastrowid)

    def set_tip_cause(self, tip_id: int, shot_id: Optional[int]) -> None:
        with self._lock:
            self._db.execute("UPDATE tips SET caused_by_shot_id=? WHERE tip_id=?",
                             (shot_id, tip_id))
            self._db.commit()

    def list_tips(self, session_id: str) -> list[TipEvent]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM tips WHERE session_id=? ORDER BY t, tip_id", (session_id,)
            ).fetchall()
        return [TipEvent(t=r["t"], session_id=r["session_id"], alliance=r["alliance"],
                         new_up_cell=r["new_up_cell"], caused_by_shot_id=r["caused_by_shot_id"])
                for r in rows]

    # -- calibration blobs (optional) -----------------------------------------
    def put_blob(self, name: str, blob: dict) -> None:
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO calibration VALUES (?,?,?)",
                             (name, json.dumps(blob), time.time()))
            self._db.commit()

    def get_blob(self, name: str) -> Optional[dict]:
        with self._lock:
            r = self._db.execute("SELECT blob FROM calibration WHERE name=?", (name,)).fetchone()
        return None if r is None else json.loads(r[0])


# -- API serialisation helpers (docs/api.md ShotSummary / full shot) -------------
def shot_summary(shot: Shot) -> dict:
    from .physics import equation_string
    clip_url = None
    if shot.clip_path:
        clip_url = "/clips/" + Path(shot.clip_path).name
    return {
        "shot_id": shot.shot_id, "t_launch": shot.t_launch, "burst_id": shot.burst_id,
        "burst_index": shot.burst_index, "ball_type": shot.ball_type.value,
        "result": shot.result.value, "exit_speed_ips": shot.exit_speed_ips,
        "exit_speed_mps": None if shot.exit_speed_ips is None
        else shot.exit_speed_ips * IPS_TO_MPS,
        "launch_angle_deg": shot.launch_angle_deg,
        "launch_azimuth_deg": shot.launch_azimuth_deg, "apex_z_in": shot.apex_z_in,
        "equation": None if shot.parabola is None else equation_string(shot.parabola),
        "clip_url": clip_url,
    }


def shot_full(shot: Shot) -> dict:
    d = shot_summary(shot)
    d["track"] = [] if shot.track is None else [
        {"t": p.t, "x": p.x, "y": p.y, "z": p.z} for p in shot.track.points]
    d["parabola"] = None if shot.parabola is None else {
        "a": shot.parabola.a, "b": shot.parabola.b, "c": shot.parabola.c,
        "rmse_in": shot.parabola.rmse_in}
    d["drag"] = None if shot.drag is None else {
        "v0": list(shot.drag.v0), "p0": list(shot.drag.p0),
        "k_per_in": shot.drag.k_per_in, "rmse_in": shot.drag.rmse_in}
    d["launch_point"] = None if shot.launch_point is None else list(shot.launch_point)
    return d

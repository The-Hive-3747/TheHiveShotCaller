"""FastAPI application implementing docs/api.md."""

from __future__ import annotations

import argparse
import asyncio
import collections
import contextlib
import json
import logging
import os
import sys
import tempfile
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from fastapi import Body, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from . import calib, calib_targets, field, ingest
from . import config as cfgmod
from .pipeline import (
    LENS_OK_RMSE_PX,
    LENS_POOR_RMSE_PX,
    ConfigConflict,
    Pipeline,
    calibration_hive_defs,
    calibration_state,
    computed_hive_defs,
)
from .resources import resource_path
from .shots import annotate, summarize
from .stats import compute_stats, shots_to_csv, stats_to_dict
from .store import Store, shot_full

log = logging.getLogger("hiveshot.app")

DEMO_REALTIME = True            # tests may set False so the demo footage runs flat out
DEMO_SESSION_TEMPLATE = "Demo {date} {time}"
MAX_SAVE_RMSE_PX = 4.0     # an extrinsics solve above this reprojection error is not saved
MAX_SAVE_OOS_IN = 2.0      # ... nor one whose held-out tags are further off than this
PAIR_HINT = "if both cameras moved, use Auto-calibrate all (or Recalibrate both)"
MAX_FINISH_OOS_IN = 1.0    # the wizard may finish only at or below this cross-check error
DROP_WINDOW_S = 60.0
DEVICE_PROBE_MAX = 6
DEVICE_CACHE_S = 30.0
DEMO_FIXTURES = ("synth_20", "synth_basic")


def demo_config() -> cfgmod.AppConfig:
    """The demo setup: two bundled synthetic videos on loop, the calibration embedded in the
    fixture truth JSON, HIVE state manual (red, audience up). Never written to config.json."""
    fx = next((f for f in DEMO_FIXTURES
               if (cfgmod.ROOT / "fixtures" / f / "cam0.mp4").exists()), DEMO_FIXTURES[-1])
    return cfgmod.AppConfig(
        sources=[cfgmod.SourceConfig(cam_id=f"cam{i}", kind="file", loop=True,
                                     realtime=DEMO_REALTIME,
                                     target=f"fixtures/{fx}/cam{i}.mp4") for i in (0, 1)],
        calibration_path="data/calibration.json",    # absent in the demo dir: fixture truth
        alliance="red", hive_up_cell="audience", session_name_template=DEMO_SESSION_TEMPLATE,
        session_idle_end_min=0.0, autosave_csv=False)

UI_DIR = resource_path("ui")
MAX_INTRINSIC_FRAMES = 40
_REQ = Body(...)
_OPT = Body(default_factory=dict)


class Refusal(Exception):
    """A request refused on purpose (HTTP 409): `detail` is the plain-language reason and
    `extra` the numbers behind it, merged into the JSON body."""

    def __init__(self, detail: str, extra: Optional[dict] = None, status: int = 409):
        super().__init__(detail)
        self.detail, self.extra, self.status = detail, dict(extra or {}), status


class _Recorder:
    """Records frames from a capture reader at ~2 fps into memory."""

    def __init__(self, reader, period_s: float = 0.5):
        self.reader = reader
        self.period_s = period_s
        self.frames: list[np.ndarray] = []
        self._stop = threading.Event()
        self._last_idx = -1
        self._th = threading.Thread(target=self._run, daemon=True, name="intr-recorder")
        self._th.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            fr = self.reader.latest()
            if fr is not None and fr.frame_idx != self._last_idx \
                    and len(self.frames) < MAX_INTRINSIC_FRAMES:
                self._last_idx = fr.frame_idx
                self.frames.append(fr.image.copy())
            self._stop.wait(self.period_s)

    def stop(self) -> list[np.ndarray]:
        self._stop.set()
        self._th.join(timeout=2)
        return self.frames


class AppState:
    def __init__(self, config_path: Path, data_dir: Path, overrides: Optional[dict] = None,
                 autostart: bool = False):
        self.config_path = Path(config_path)
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "clips").mkdir(parents=True, exist_ok=True)
        self.cfg = cfgmod.load(self.config_path)
        if overrides:
            self.cfg = cfgmod.AppConfig.model_validate(cfgmod.merge(self.cfg.to_dict(), overrides))
        self.autostart = autostart
        self.demo = False
        self._user: Optional[dict] = None       # the user's state while the demo runs
        self.store = Store(self.data_dir / "hiveshot.db")
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.clients: set[WebSocket] = set()
        self.pipeline = Pipeline(self.cfg, self.store, self.data_dir, on_event=self.on_event)
        self.recorders: dict[str, _Recorder] = {}
        self.lock = threading.Lock()
        self._drop_hist: collections.deque = collections.deque()
        self._dev_cache: Optional[tuple[float, set, list]] = None
        # last extrinsics click set per camera: {cam_id: [{name, u, v}]} (image pixels)
        self.clicks: dict[str, list[dict]] = self._load_clicks()
        # tags each camera's last tag-based extrinsics solve used: {cam: {source, tags_used}}
        # (a click-based solve stores {source: "clicks", tags_used: []}); the out-of-sample
        # crosscheck holds out every tag a solve did not use
        self.solve_tags: dict[str, dict] = {str(k): dict(v) for k, v in
                                            self._load_extra("solve_tags").items()}
        # learned HIVE tag corners per state: {"red_audience": {"34": [[x,y,z] x4]}}
        self.hive_tags: dict[str, dict[str, list]] = self._load_extra("hive_tags")

    def _calib_path(self) -> Path:
        return cfgmod.resolve_path(self.cfg.calibration_path, self.data_dir)

    def _load_extra(self, key: str) -> dict:
        try:
            data = json.loads(self._calib_path().read_text(encoding="utf-8"))
            return dict(data.get(key) or {})
        except (OSError, ValueError, AttributeError):
            return {}

    def _load_clicks(self) -> dict[str, list[dict]]:
        return {str(k): list(v) for k, v in self._load_extra("clicks").items()}

    # events from pipeline threads -> websocket clients
    def on_event(self, ev: dict) -> None:
        loop = self.loop
        if loop is None or loop.is_closed():
            return
        asyncio.run_coroutine_threadsafe(self.broadcast(ev), loop)

    async def broadcast(self, msg: dict) -> None:
        for ws in list(self.clients):
            try:
                await ws.send_json(msg)
            except Exception:  # noqa: BLE001
                self.clients.discard(ws)

    def status_msg(self) -> dict:
        status = self.pipeline.status()
        self.note_drops(status)
        return {"type": "status", **status}

    # ------------------------------------------------ setup helpers (devices, dropped frames)
    def note_drops(self, status: dict) -> None:
        """Remember the cumulative dropped-frame counters, to tell recent drops from old."""
        now = time.monotonic()
        with self.lock:
            if not status.get("running"):
                self._drop_hist.clear()
                return
            self._drop_hist.append((now, {c: int(v.get("dropped") or 0)
                                          for c, v in status["cameras"].items()}))
            while self._drop_hist and now - self._drop_hist[0][0] > DROP_WINDOW_S + 5.0:
                self._drop_hist.popleft()

    def recent_drops(self, status: dict) -> dict[str, int]:
        """Frames dropped per camera in the last DROP_WINDOW_S (counters start at 0 when the
        pipeline starts, so before a full window of samples the baseline is 0)."""
        self.note_drops(status)
        now = time.monotonic()
        with self.lock:
            hist = list(self._drop_hist)
        if not hist:
            return {}
        last = hist[-1][1]
        older = [h for h in hist if now - h[0] >= DROP_WINDOW_S]
        base = older[-1][1] if older else {}
        return {c: n - base.get(c, 0) for c, n in last.items() if n - base.get(c, 0) > 0}

    def free_devices(self, busy: set[int]) -> list[dict]:
        """Capture devices on this PC (30 s cache) without touching indexes the pipeline has
        open: `ingest.list_devices` when nothing is busy, else a probe of the free indexes."""
        if not busy:
            return [dict(d) for d in ingest.list_devices(max_index=DEVICE_PROBE_MAX)]
        now = time.monotonic()
        with self.lock:
            c = self._dev_cache
        if c is not None and now - c[0] < DEVICE_CACHE_S and c[1] == busy:
            return [dict(d) for d in c[2]]
        found: list[dict] = []
        for i in range(DEVICE_PROBE_MAX):
            if i in busy:
                continue
            out: dict = {}
            th = threading.Thread(target=ingest._probe_one, args=(i, out), daemon=True)
            th.start()
            th.join(2.5 if i == 0 else 1.0)
            if not th.is_alive() and "info" in out:
                found.append(out["info"])
        with self.lock:
            self._dev_cache = (now, set(busy), [dict(d) for d in found])
        return found

    def save_cfg(self) -> None:
        if self.demo:
            return          # the demo config is never persisted
        cfgmod.save(self.config_path, self.cfg)

    # ------------------------------------------------------------------ demo mode
    def start_demo(self) -> str:
        """Swap to the demo setup (own data dir `<data>/demo`, own database, in-memory
        config), start it and open a "Demo ..." session. Returns the session id."""
        with self.lock:
            if self._user is None and not self.demo:
                self.pipeline.stop()
                demo_dir = self.data_dir / "demo"
                demo_dir.mkdir(parents=True, exist_ok=True)
                (demo_dir / "clips").mkdir(exist_ok=True)
                cfg = demo_config()
                store = Store(demo_dir / "hiveshot.db")
                self._user = {"cfg": self.cfg, "pipeline": self.pipeline, "store": self.store,
                              "data_dir": self.data_dir, "clicks": self.clicks,
                              "hive_tags": self.hive_tags, "solve_tags": self.solve_tags}
                self.cfg, self.store, self.data_dir = cfg, store, demo_dir
                self.pipeline = Pipeline(cfg, store, demo_dir, on_event=self.on_event,
                                         demo=True)
                self.clicks, self.hive_tags, self.solve_tags = {}, {}, {}
                self.demo = True
            else:
                self.pipeline.stop()        # demo already active: restart it
            self.demo = True
            self.pipeline.demo = True
            for sid in self.store.open_sessions():
                self.store.end_session(sid)
            sid = self.store.create_session(
                cfgmod.format_session_name(DEMO_SESSION_TEMPLATE))
            self.pipeline.set_session(sid)
            self.pipeline.start()
            return sid

    def stop_demo(self) -> None:
        """Stop the demo and restore the user's config, pipeline and database."""
        with self.lock:
            self.pipeline.stop()
            if self._user is not None:
                u, self._user = self._user, None
                self.store.close()
                self.cfg, self.pipeline, self.store = u["cfg"], u["pipeline"], u["store"]
                self.data_dir, self.clicks, self.hive_tags = (
                    u["data_dir"], u["clicks"], u["hive_tags"])
                self.solve_tags = u["solve_tags"]
            self.demo = False
            self.pipeline.demo = False

    def shutdown(self) -> None:
        """Stop everything (demo and user pipelines) and close the databases."""
        try:
            self.pipeline.stop()
        finally:
            self.store.close()
            if self._user is not None:
                try:
                    self._user["pipeline"].stop()
                finally:
                    self._user["store"].close()

    def calib_dict(self) -> dict:
        intr, ext = self.pipeline.calibration()
        stale = self.pipeline.stale_extrinsics()
        return {"version": 1, "calibration_state": calibration_state(),
                "intrinsics": [{**i.__dict__, "dist": list(i.dist)} for i in intr.values()],
                "extrinsics": [{**e.__dict__, "rvec": list(e.rvec), "tvec": list(e.tvec),
                                "stale": e.cam_id in stale} for e in ext.values()]}

    def save_calib(self, intr: dict, ext: dict, stale: Optional[set] = None,
                   measured: Optional[set] = None) -> None:
        """Write the calibration JSON. Extrinsics of cameras in `stale` get ``stale: true``
        (their intrinsics changed after they were solved); load tolerates the extra key."""
        path = self._calib_path()
        calib.save_calibration(path, list(intr.values()), list(ext.values()))
        stale = set(stale or ()) & set(ext)
        data = json.loads(path.read_text(encoding="utf-8"))
        for e in data["extrinsics"]:
            if e["cam_id"] in stale:
                e["stale"] = True
        # clicks of cameras whose extrinsics still exist survive any calibration save
        self.clicks = {c: v for c, v in self.clicks.items() if c in ext}
        if self.clicks:
            data["clicks"] = self.clicks
        if self.hive_tags:
            data["hive_tags"] = self.hive_tags
        self.solve_tags = {c: v for c, v in self.solve_tags.items() if c in ext}
        if self.solve_tags:
            data["solve_tags"] = self.solve_tags
        # where each camera's lens intrinsics came from; "default" keeps its warning alive
        src = {c: v for c, v in self.pipeline.intrinsics_sources().items() if c in intr}
        for c in (measured or ()):
            src[c] = measured[c] if isinstance(measured, dict) else "measured"
        data["intrinsics_source"] = {c: src.get(c, "measured") for c in intr}
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.pipeline.reload_calibration()


def create_app(config_path: Optional[Path | str] = None, data_dir: Optional[Path | str] = None,
               overrides: Optional[dict] = None, autostart: bool = False,
               demo: bool = False) -> FastAPI:
    """`demo=True` (the --demo flag): the whole app lives in `<data_dir>/demo` and the demo
    pipeline starts with the server; the user's config.json and database are not opened."""
    dd = Path(data_dir) if data_dir else cfgmod.default_data_dir()
    if demo:
        dd = dd / "demo"
        cp = dd / "demo_config.json"          # never read or written in demo mode
        overrides = demo_config().to_dict()
    else:
        cp = Path(config_path) if config_path else dd / "config.json"
    st = AppState(cp, dd, overrides, autostart)
    st.demo = demo
    st.pipeline.demo = demo

    async def status_task() -> None:
        while True:
            await asyncio.sleep(1.0)
            if st.clients:
                await st.broadcast(st.status_msg())

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        st.loop = asyncio.get_running_loop()
        # sessions left open by a previous run (crash or kill) are over: close them before
        # autostart creates a new one
        for sid in st.store.open_sessions():
            st.store.end_session(sid)
        task = asyncio.create_task(status_task())
        if demo:
            try:
                await asyncio.to_thread(st.start_demo)
            except Exception:  # noqa: BLE001
                log.exception("demo start failed")
        elif st.autostart:
            try:
                await asyncio.to_thread(st.pipeline.start)
            except Exception:  # noqa: BLE001
                log.exception("autostart failed")
        try:
            yield
        finally:
            task.cancel()
            # stop() joins every worker and flushes; only then are the stores closed
            await asyncio.to_thread(st.shutdown)

    app = FastAPI(title="HiveShotTracker", lifespan=lifespan)
    app.state.hs = st

    def _session_start(session_id: str) -> Optional[float]:
        return (st.store.session_summary(session_id) or {}).get("started_at")

    def _need_session(session_id: str) -> None:
        if not st.store.session_exists(session_id):
            raise HTTPException(404, f"unknown session {session_id}")

    # ------------------------------------------------------------- sessions
    @app.get("/api/sessions")
    def sessions_list():
        return st.store.list_sessions()

    @app.post("/api/sessions")
    def sessions_create(body: dict = _OPT):
        name = str(body.get("name") or cfgmod.format_session_name(st.cfg.session_name_template))
        for sid in st.store.open_sessions():
            st.store.end_session(sid)
        sid = st.store.create_session(name)
        st.pipeline.set_session(sid)
        return {"session_id": sid}

    @app.post("/api/sessions/{session_id}/end")
    def sessions_end(session_id: str):
        _need_session(session_id)
        st.store.end_session(session_id)
        if st.pipeline.session_id == session_id:
            st.pipeline.set_session(None)
        return {"ok": True}

    @app.get("/api/sessions/{session_id}/stats")
    def sessions_stats(session_id: str):
        _need_session(session_id)
        return stats_to_dict(compute_stats(st.store.list_shots(session_id),
                                           st.store.list_tips(session_id), session_id))

    @app.get("/api/sessions/{session_id}/shots")
    def sessions_shots(session_id: str):
        _need_session(session_id)
        started = _session_start(session_id)
        return [summarize(s, started) for s in st.store.list_shots(session_id)]

    @app.get("/api/sessions/{session_id}/export.csv")
    def sessions_csv(session_id: str):
        _need_session(session_id)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "shots.csv"
            shots_to_csv(st.store.list_shots(session_id), p, _session_start(session_id))
            text = p.read_text(encoding="utf-8")
        return Response(text, media_type="text/csv", headers={
            "Content-Disposition": f'attachment; filename="session_{session_id}.csv"'})

    @app.get("/api/shots/{shot_id}")
    def shots_get(shot_id: int):
        s = st.store.get_shot(shot_id)
        if s is None:
            raise HTTPException(404, f"unknown shot {shot_id}")
        return annotate(shot_full(s), s, _session_start(s.session_id))

    @app.get("/api/sessions/{session_id}/tips")
    def sessions_tips(session_id: str):
        _need_session(session_id)
        return [{"t": t.t, "alliance": t.alliance, "new_up_cell": t.new_up_cell,
                 "caused_by_shot_id": t.caused_by_shot_id}
                for t in st.store.list_tips(session_id)]

    # ------------------------------------------------------------ config etc.
    @app.get("/api/config")
    def config_get():
        return st.cfg.to_dict()

    @app.put("/api/config")
    def config_put(patch: dict = _REQ):
        try:
            new = cfgmod.AppConfig.model_validate(cfgmod.merge(st.cfg.to_dict(), patch))
            field.HiveState(new.alliance, new.hive_up_cell)
        except (ValidationError, ValueError) as e:
            raise HTTPException(422, str(e)) from e
        with st.lock:
            try:
                deferred = st.pipeline.apply_config(new)
            except ConfigConflict as e:
                raise HTTPException(409, str(e)) from e
            st.cfg = new
            st.save_cfg()
            if not st.pipeline.running:
                st.pipeline.reload_calibration()
        if deferred:
            log.info("config keys applied at next pipeline start: %s", deferred)
        return new.to_dict()

    @app.get("/api/devices")
    def devices(max_index: int = 10):
        return [{"index": d["index"], "width": d["width"], "height": d["height"],
                 "fps": d["fps"]} for d in ingest.list_devices(max_index=max_index)]

    @app.post("/api/demo/start")
    def demo_start():
        """Swap to the bundled demo (separate data dir, in-memory config) and start it."""
        try:
            sid = st.start_demo()
        except Exception as e:  # noqa: BLE001
            log.exception("demo start failed")
            raise HTTPException(500, f"demo start failed: {e}") from e
        return {"ok": True, "session_id": sid}

    @app.post("/api/demo/stop")
    def demo_stop():
        """Stop the demo and restore the saved user config."""
        st.stop_demo()
        return {"ok": True}

    @app.post("/api/pipeline/start")
    def pipeline_start():
        try:
            st.pipeline.start()
        except Exception as e:  # noqa: BLE001
            log.exception("pipeline start failed")
            raise HTTPException(500, f"pipeline start failed: {e}") from e
        return {"ok": True, "running": True}

    @app.post("/api/pipeline/stop")
    def pipeline_stop():
        st.pipeline.stop()
        return {"ok": True, "running": False}

    @app.get("/api/pipeline/status")
    def pipeline_status():
        return st.pipeline.status()

    @app.post("/api/hive/state")
    def hive_state(body: dict = _REQ):
        try:
            h = st.pipeline.set_hive_state(str(body.get("alliance", st.cfg.alliance)),
                                           str(body.get("up_cell", st.cfg.hive_up_cell)),
                                           source="manual")
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        st.cfg = st.cfg.model_copy(update={"alliance": h.alliance, "hive_up_cell": h.up_cell})
        st.pipeline.cfg = st.cfg
        st.save_cfg()
        return {"alliance": h.alliance, "up_cell": h.up_cell}

    # --------------------------------------------------------------- preview
    def _known_cam(cam_id: str) -> None:
        if cam_id not in {s.cam_id for s in st.cfg.sources}:
            raise HTTPException(404, f"unknown camera {cam_id}")

    @app.get("/api/preview/{cam_id}.jpg")
    def preview_jpg(cam_id: str):
        # Raw full-resolution latest frame (unannotated) so calibration clicks map 1:1.
        # 404 while the pipeline is not running / no frame has arrived yet.
        _known_cam(cam_id)
        buf = st.pipeline.raw_jpeg(cam_id)
        if buf is None:
            raise HTTPException(404, "no frame available (pipeline not running?)")
        fr = st.pipeline.latest_frame(cam_id)
        h, w = fr.image.shape[:2]
        return Response(buf, media_type="image/jpeg", headers={
            "Cache-Control": "no-store", "X-Frame-Width": str(w), "X-Frame-Height": str(h)})

    @app.get("/api/preview/{cam_id}.mjpg")
    async def preview_mjpg(cam_id: str, request: Request):
        _known_cam(cam_id)
        if not st.pipeline.running:
            raise HTTPException(404, "pipeline not running")

        async def gen():
            last = None
            period = 1.0 / 15.0
            # the pipeline only encodes preview JPEGs while at least one client is attached
            st.pipeline.preview_client_add(cam_id)
            try:
                while st.pipeline.running:
                    if await request.is_disconnected():
                        break
                    buf = st.pipeline.latest_jpeg(cam_id)
                    if buf is not None and buf is not last:
                        last = buf
                        yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                               + str(len(buf)).encode() + b"\r\n\r\n" + buf + b"\r\n")
                    await asyncio.sleep(period)
            finally:
                st.pipeline.preview_client_remove(cam_id)

        return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame",
                                 headers={"Cache-Control": "no-store"})

    # ----------------------------------------------------------- calibration
    @app.get("/api/calib")
    def calib_get():
        return st.calib_dict()

    @app.get("/api/calib/checkerboard.pdf")
    def calib_checkerboard():
        name = "checkerboard_10x7_1in.pdf"
        path = st.data_dir / name
        with st.lock:
            if not path.exists():
                calib_targets.write_checkerboard_pdf(path, 10, 7, 1.0)
            data = path.read_bytes()
        return Response(data, media_type="application/pdf", headers={
            "Content-Disposition": f'attachment; filename="{name}"'})

    @app.get("/api/calib/points")
    def calib_points():
        return [{"name": n, "xyz": [float(v) for v in xyz]}
                for n, xyz in calib_targets.field_reference_points()]

    def _expected_points() -> dict[str, tuple]:
        """Known field positions by click name: the 8 reference points and, when the tag
        kit is available, every kit tag corner ("tag 100 corner 0")."""
        exp = {n: p for n, p in calib_targets.field_reference_points()}
        try:
            from . import tagkit
            for t in tagkit.KIT_TAGS:
                for k, p in enumerate(tagkit.tag_corners_xyz(t)):
                    exp[f"tag {t.id} corner {k}"] = tuple(float(v) for v in p)
        except ImportError:
            pass
        return exp

    @app.post("/api/calib/crosscheck")
    def calib_crosscheck(body: dict = _OPT):
        """Out-of-sample check of the two cameras' calibration: triangulate AprilTag corners
        that no extrinsics solve used and compare them with their known field positions.
        `{"in_sample": true}` re-measures the clicked/solved points instead."""
        return _crosscheck(in_sample=bool(body.get("in_sample")))

    def _expected_tags() -> dict[int, tuple[np.ndarray, str]]:
        """Known corners {id: ((4,3) field corners, "kit" | "hive")} of every tag with a
        known position: the printed kit and the computed HIVE tags of the current state."""
        expected: dict[int, tuple[np.ndarray, str]] = {}
        try:
            from . import tagkit
            for tid, c4 in tagkit.tag_defs().items():
                expected[int(tid)] = (np.asarray(c4, float).reshape(4, 3), "kit")
        except ImportError:
            pass
        for tid, c4 in calibration_hive_defs().items():
            expected[int(tid)] = (c4, "hive")
        return expected

    def _held_out_points(cams, intr, ext, solve_tags=None) -> tuple[list[dict], str]:
        """Held-out features visible in the latest frame of both cameras: the HIVE tags
        (computed CAD corners for the current HIVE state) and the kit tags that neither
        camera's solve used. Returns (points, what) or ([], reason)."""
        a, b = cams
        fa, fb = st.pipeline.latest_frame(a), st.pipeline.latest_frame(b)
        if fa is None or fb is None:
            return [], "the pipeline is not running (no frames)"
        recorded = st.solve_tags if solve_tags is None else solve_tags
        info = [recorded.get(c) for c in cams]
        if not all(info):
            return [], "it is not known which tags the extrinsics solves used"
        used = {int(t) for i in info for t in i.get("tags_used", [])}
        expected = _expected_tags()
        da = {int(d["id"]): d["corners"] for d in calib.detect_apriltags(fa.image)}
        db = {int(d["id"]): d["corners"] for d in calib.detect_apriltags(fb.image)}
        ids = sorted(i for i in set(da) & set(db) if i in expected and i not in used)
        if not ids:
            return [], "no tag outside the solves is visible in both cameras"
        uv_a = np.vstack([np.asarray(da[i], float).reshape(4, 2) for i in ids])
        uv_b = np.vstack([np.asarray(db[i], float).reshape(4, 2) for i in ids])
        xyz, resid = calib.triangulate(intr[a], ext[a], uv_a, intr[b], ext[b], uv_b)
        pts = []
        for n, (tid, k) in enumerate((i, k) for i in ids for k in range(4)):
            exp, kind = expected[tid]
            m = np.asarray(xyz[n], float)
            pts.append({"name": f"{'hive tag' if kind == 'hive' else 'tag'} {tid} corner {k}",
                        "kind": kind, "xyz_measured": [float(v) for v in m],
                        "xyz_expected": [float(v) for v in exp[k]],
                        "error_in": float(np.linalg.norm(m - exp[k])),
                        "residual_in": float(resid[n])})
        kinds = sorted({p["kind"] for p in pts})
        what = " and ".join({"hive": "HIVE tags", "kit": "kit tags"}[k] for k in kinds)
        return pts, what

    def _oos_camera_error(intr_c, ext_c, image, used_ids) -> Optional[float]:
        """Out-of-sample error of ONE camera, in inches: for every tag corner the camera sees
        that its own solve did not use, the distance between the known 3D corner and the
        camera ray through the detected pixel. Max over the corners; None if no such tag."""
        expected = _expected_tags()
        dets = {int(d["id"]): d["corners"] for d in calib.detect_apriltags(image)}
        ids = [i for i in sorted(dets) if i in expected and i not in used_ids]
        if not ids:
            return None
        R, t = calib._rt(ext_c)
        centre = -R.T @ t
        worst = 0.0
        for i in ids:
            norm = calib.undistort_points(intr_c, np.asarray(dets[i], float).reshape(4, 2),
                                          normalized=True)
            for k in range(4):
                d = R.T @ np.array([norm[k, 0], norm[k, 1], 1.0])
                d /= np.linalg.norm(d)
                worst = max(worst, float(np.linalg.norm(np.cross(expected[i][0][k] - centre, d))))
        return worst

    def _gate_extrinsics(cam_id: str, intr_c, ext_new, rmse_px: Optional[float],
                         record: dict, image: Optional[np.ndarray],
                         force_single: bool = False) -> tuple[Optional[float], Optional[str]]:
        """Refuse (409 with the numbers) to save an extrinsics solve that is clearly wrong:
        reprojection RMSE over MAX_SAVE_RMSE_PX, a frame whose size is not the intrinsics'
        size, or an out-of-sample error (this camera's, and the pair's when both cameras are
        calibrated) over MAX_SAVE_OOS_IN. `force_single` skips only the pair check. Returns
        (this camera's out-of-sample error, the other camera to mark pair-stale or None)."""
        numbers: dict = {"cam_id": cam_id, "reprojection_px": rmse_px}
        reasons = []
        if rmse_px is not None and rmse_px > MAX_SAVE_RMSE_PX:
            reasons.append(f"reprojection error {rmse_px:.1f} px is over {MAX_SAVE_RMSE_PX:.0f} px "
                           "(wrong tag positions, a moved tag, or the wrong lens intrinsics)")
        if image is not None:
            h, w = image.shape[:2]
            numbers["frame_size"] = [int(w), int(h)]
            numbers["intrinsics_size"] = [int(intr_c.width), int(intr_c.height)]
            if (w, h) != (intr_c.width, intr_c.height):
                reasons.append(f"the camera delivers {w}x{h} but its intrinsics are for "
                               f"{intr_c.width}x{intr_c.height}: redo the intrinsics or fix the "
                               "camera resolution")
        oos = None
        stale_other: Optional[str] = None
        pair_failed = False
        if image is not None:
            oos = _oos_camera_error(intr_c, ext_new, image, set(record.get("tags_used", [])))
            numbers["oos_error_in"] = oos
            if oos is not None and oos > MAX_SAVE_OOS_IN:
                reasons.append(f"a tag that was not used for the solve is {oos:.1f} in off "
                               f"(limit {MAX_SAVE_OOS_IN:.0f} in)")
            cams = [c.cam_id for c in st.cfg.sources][:2]
            intr, ext = st.pipeline.calibration()
            if cam_id in cams and len(cams) == 2:
                other = cams[1 - cams.index(cam_id)]
                if other in ext and other in intr and not reasons:
                    pair_ext = {**ext, cam_id: ext_new}
                    pts, _what = _held_out_points(cams, intr, pair_ext,
                                                  {**st.solve_tags, cam_id: record})
                    if pts:
                        worst = max(p["error_in"] for p in pts)
                        numbers["crosscheck_error_in"] = worst
                        if worst > MAX_SAVE_OOS_IN:
                            if force_single:
                                stale_other = other        # accepted alone; flagged below
                            else:
                                pair_failed = True
                                reasons.append(f"the out-of-sample cross-check with {other} would "
                                               f"be {worst:.1f} in (limit {MAX_SAVE_OOS_IN:.0f} in)")
        if reasons:
            if pair_failed:
                numbers["hint"] = PAIR_HINT
                numbers["pair_check_failed"] = True
            raise Refusal(f"extrinsics of {cam_id} not saved: " + "; ".join(reasons)
                          + ". The previous calibration is kept."
                          + (" Hint: " + PAIR_HINT + "." if pair_failed else ""), numbers)
        return oos, stale_other

    def _crosscheck(in_sample: bool = False) -> dict:
        cams = [s.cam_id for s in st.cfg.sources][:2]
        intr, ext = st.pipeline.calibration()
        if len(cams) < 2 or not all(c in intr and c in ext for c in cams):
            raise HTTPException(409, "need intrinsics and extrinsics for both cameras")
        why = "in-sample re-measurement was requested"
        if not in_sample:
            pts, what = _held_out_points(cams, intr, ext)
            if pts:
                worst = max(p["error_in"] for p in pts)
                return {"points": pts, "max_error_in": worst, "within_1_in": worst <= 1.0,
                        "out_of_sample": True, "held_out": what}
            why = what
        missing = [c for c in cams if not st.clicks.get(c)]
        if missing:
            lead = "" if in_sample else f"no held-out feature to check ({why}) and "
            raise HTTPException(
                409, lead + "no stored extrinsics clicks for " + ", ".join(missing)
                + "; solve the extrinsics of both cameras first")
        a, b = cams
        ca = {c["name"]: c for c in st.clicks[a]}
        cb = {c["name"]: c for c in st.clicks[b]}
        expected = _expected_points()
        names = [n for n in expected if n in ca and n in cb]
        if not names:
            raise HTTPException(422, "no reference point was clicked in both cameras")
        xyz, resid = calib.triangulate(
            intr[a], ext[a], np.array([[ca[n]["u"], ca[n]["v"]] for n in names]),
            intr[b], ext[b], np.array([[cb[n]["u"], cb[n]["v"]] for n in names]))
        pts = []
        for n, m, r in zip(names, xyz, resid, strict=True):
            e = np.array(expected[n], float)
            pts.append({"name": n, "xyz_measured": [float(v) for v in m],
                        "xyz_expected": [float(v) for v in e],
                        "error_in": float(np.linalg.norm(m - e)), "residual_in": float(r)})
        worst = max(p["error_in"] for p in pts)
        out = {"points": pts, "max_error_in": worst, "within_1_in": worst <= 1.0,
               "out_of_sample": False}
        if not in_sample:
            out["warning"] = ("in-sample: these are the points the extrinsics were solved from, "
                              "so the error is optimistic (no held-out feature: " + why + ")")
        return out

    # --------------------------------------------- setup wizard, tags, auto-calibration
    def _tagkit():
        try:
            from . import tagkit
            return tagkit
        except ImportError as e:
            raise HTTPException(503, f"AprilTag kit is not available in this build: {e}") from e

    @app.get("/api/calib/tags")
    def calib_tags():
        return _tagkit().tags_json()

    @app.get("/api/calib/tags.pdf")
    def calib_tags_pdf():
        tk = _tagkit()
        name = "hive_calibration_tags.pdf"
        data = tk.tag_sheet_pdf_bytes()
        return Response(data, media_type="application/pdf", headers={
            "Content-Disposition": f'attachment; filename="{name}"'})

    def _auto_solve(cam_id: str, body: dict) -> dict:
        tk = _tagkit()
        if not hasattr(calib, "solve_extrinsics_from_tags"):
            raise HTTPException(503, "tag-based extrinsics are not available in this build")
        _known_cam(cam_id)
        fr = st.pipeline.latest_frame(cam_id)
        if fr is None:
            raise HTTPException(409, f"no frame from {cam_id}: start the pipeline first")
        old_i, old_e = st.pipeline.calibration()
        if cam_id not in old_i:
            raise HTTPException(409, f"no intrinsics for {cam_id}; calibrate intrinsics first")
        source = str(body.get("source") or ("hive" if body.get("use_hive_tags") else "both")).lower()
        if source not in ("kit", "hive", "both"):
            raise HTTPException(422, "source must be 'kit', 'hive' or 'both'")
        defs: dict[int, np.ndarray] = {}
        if source in ("kit", "both"):
            defs.update(tk.tag_defs())
        if source in ("hive", "both"):
            # both alliances' tags in the calibration state (both audience CELLs up), not the
            # pipeline's current HIVE state; learned positions of that state win
            defs.update(calibration_hive_defs())
            for al, up in calibration_state().items():
                defs.update({int(i): np.asarray(c, float)
                             for i, c in (st.hive_tags.get(f"{al}_{up}") or {}).items()})
        if source == "hive" and not defs:
            raise HTTPException(422, "no HIVE tag positions are known for the current state; "
                                "learn them first (POST /api/calib/hive_tags/learn)")
        try:
            ext, info = calib.solve_extrinsics_from_tags(
                old_i[cam_id], fr.image, defs, cam_id, min_tags=2)
        except ValueError as e:
            msg = str(e)
            if source == "hive" and "tags visible" in msg:
                msg = (f"no HIVE tags visible to {cam_id} (need at least 2 of ids "
                       f"{sorted(defs)}); only cameras that can read the HIVE tags can be "
                       "calibrated from them")
            raise HTTPException(422, msg) from e
        kit_ids = [t for t in info["tags_used"] if 100 <= t <= 103]
        hive_used = [t for t in info["tags_used"] if t not in kit_ids]
        record = {"source": source, "tags_used": [int(t) for t in info["tags_used"]]}
        was_default = st.pipeline.intrinsics_sources().get(cam_id) == "default"
        oos, stale_other = _gate_extrinsics(cam_id, old_i[cam_id], ext, info["reprojection_px"],
                                            record, fr.image,
                                            force_single=bool(body.get("force_single")))
        if kit_ids:
            corners = {int(d["id"]): d["corners"] for d in calib.detect_apriltags(fr.image)}
            st.clicks[cam_id] = [
                {"name": f"tag {tid} corner {k}", "u": float(u), "v": float(v)}
                for tid in kit_ids for k, (u, v) in enumerate(corners[tid])]
        else:
            st.clicks.pop(cam_id, None)          # the old kit clicks belong to an older pose
        st.solve_tags[cam_id] = record
        warnings = []
        if not kit_ids:
            warnings.append("calibrated from HIVE tags only: expect 2-3x lower accuracy than "
                            "the kit")
        st.save_calib(old_i, {**old_e, cam_id: ext},
                      st.pipeline.stale_extrinsics() - {cam_id})
        st.pipeline.set_pair_stale(cam_id, False)
        if stale_other:
            st.pipeline.set_pair_stale(stale_other, True)
            warnings.append(f"the pair check with {stale_other} failed and was skipped "
                            f"(force_single): {stale_other} is marked pair_stale until it is "
                            "re-solved; use Auto-calibrate all")
        if oos is None:
            warnings.append("no tag outside this solve is visible to this camera: the result "
                            "is not independently checked")
        if was_default:
            warnings.append("this camera still uses default lens intrinsics: run the Lens step")
        return {"rmse_in": ext.rmse_in, "fit_residual_in": ext.rmse_in, "oos_error_in": oos,
                "tags_used": info["tags_used"],
                "tags_missing": info.get("tags_missing", []),
                "reprojection_px": info["reprojection_px"],
                "max_corner_px": info.get("max_corner_px"),
                "hive_tags_used": bool(hive_used), "source": source, "warnings": warnings,
                "intrinsics_default": was_default}

    @app.post("/api/calib/extrinsics/{cam_id}/auto")
    def extr_auto(cam_id: str, body: dict = _OPT):
        # body {"use_hive_tags": true}: solve from the learned HIVE tags of the current state
        return _auto_solve(cam_id, body)

    @app.post("/api/calib/auto_all")
    def calib_auto_all(body: dict = _OPT):
        _tagkit()
        if not st.pipeline.running:
            raise HTTPException(409, "start the pipeline first (frames come from the cameras)")
        cams = [s.cam_id for s in st.cfg.sources]
        pair = cams[:2]
        # Both cameras are re-solved together: drop their old poses first (kept for rollback),
        # so neither solve is checked against the other camera's OLD pose, and the pair check
        # of the second solve runs against the NEW first pose.
        snapshot = _snapshot_poses(pair)
        if snapshot["ext"]:
            _drop_poses(pair)
        results: dict[str, dict] = {}
        for cam in cams:
            try:
                if body.get("source") or body.get("use_hive_tags"):
                    results[cam] = {"ok": True, **_auto_solve(cam, body)}
                else:
                    # kit first, so the HIVE tags stay out of the solve and can be held out
                    # by the crosscheck; a camera that cannot read the kit uses the HIVE tags
                    try:
                        results[cam] = {"ok": True, **_auto_solve(cam, {**body, "source": "kit"})}
                    except HTTPException as first:
                        if first.status_code != 422:
                            raise
                        try:
                            results[cam] = {"ok": True,
                                            **_auto_solve(cam, {**body, "source": "hive"})}
                        except HTTPException:
                            raise first from None
            except HTTPException as e:
                results[cam] = {"ok": False, "status": e.status_code, "error": e.detail}
            except Refusal as e:
                results[cam] = {"ok": False, "status": e.status, "error": e.detail, "refused": True,
                                **e.extra}
        check = None
        if len(cams) >= 2 and all(results[c]["ok"] for c in cams[:2]):
            try:
                check = _crosscheck()
            except HTTPException as e:
                check = {"error": e.detail}
        ok = all(r["ok"] for r in results.values())
        rolled_back = False
        if ok and check and check.get("out_of_sample") and check["max_error_in"] > MAX_SAVE_OOS_IN:
            ok = False
            results[pair[1]] = {**results[pair[1]], "ok": False, "status": 409, "refused": True,
                                "error": (f"the out-of-sample cross-check of the new pair is "
                                          f"{check['max_error_in']:.1f} in (limit "
                                          f"{MAX_SAVE_OOS_IN:.0f} in)")}
        if not ok:
            # all or nothing: put both old poses back (or none, on a first calibration)
            _restore_poses(pair, snapshot)
            rolled_back = True
        else:
            for c in pair:
                st.pipeline.set_pair_stale(c, False)
        warnings: list[str] = []
        for c, r in results.items():
            warnings += [f"{c}: {w}" for w in r.get("warnings", [])]
        if rolled_back:
            warnings.append("not saved: one camera failed, so both old poses were restored"
                            if snapshot["ext"] else "not saved: one camera failed")
        if check and check.get("warning"):
            warnings.append(check["warning"])
        return {"results": results, "crosscheck": check, "warnings": warnings,
                "max_error_in": None if not check else check.get("max_error_in"),
                "rolled_back": rolled_back, "ok": ok}

    def _snapshot_poses(cams: list) -> dict:
        _intr, ext = st.pipeline.calibration()
        return {"ext": {c: ext[c] for c in cams if c in ext},
                "clicks": {c: [dict(p) for p in st.clicks[c]] for c in cams if c in st.clicks},
                "solve": {c: dict(st.solve_tags[c]) for c in cams if c in st.solve_tags},
                "stale": set(st.pipeline.stale_extrinsics()) & set(cams)}

    def _drop_poses(cams: list) -> None:
        intr, ext = st.pipeline.calibration()
        keep = {c: e for c, e in ext.items() if c not in cams}
        st.save_calib(intr, keep, st.pipeline.stale_extrinsics() - set(cams))

    def _restore_poses(cams: list, snap: dict) -> None:
        intr, ext = st.pipeline.calibration()
        for c in cams:
            st.clicks.pop(c, None)
            st.solve_tags.pop(c, None)
        st.clicks.update(snap["clicks"])
        st.solve_tags.update(snap["solve"])
        keep = {c: e for c, e in ext.items() if c not in cams}
        keep.update(snap["ext"])
        st.save_calib(intr, keep, (st.pipeline.stale_extrinsics() - set(cams)) | snap["stale"])

    @app.post("/api/calib/reset")
    def calib_reset(body: dict = _OPT):
        """Delete extrinsics (poses) and keep the intrinsics: `{"cam_id": "all"|"cam0"}` or
        `{"cameras": [...]|"all"}`. Returns what was removed so it can be put back."""
        want = body.get("cameras", body.get("cam_id", "all"))
        all_cams = [s.cam_id for s in st.cfg.sources]
        if want in ("all", None):
            targets = list(all_cams)
        else:
            targets = [want] if isinstance(want, str) else [str(c) for c in want]
        for c in targets:
            _known_cam(c)
        snap = _snapshot_poses(targets)
        if snap["ext"]:
            _drop_poses(targets)
        for c in targets:
            st.pipeline.set_pair_stale(c, False)
        return {"ok": True, "reset": sorted(snap["ext"]), "cameras": targets,
                "kept": "intrinsics",
                "rollback": {
                    "extrinsics": [{**e.__dict__, "rvec": list(e.rvec), "tvec": list(e.tvec)}
                                   for e in snap["ext"].values()],
                    "solve_tags": snap["solve"], "clicks": snap["clicks"]}}

    def _hive_ids() -> list[int]:
        from .field_constants import APRILTAG_IDS
        return sorted({i for ids in APRILTAG_IDS.values() for i in ids})

    @app.post("/api/calib/hive_tags/learn")
    def hive_tags_learn(body: dict = _OPT):
        """With the HIVE settled in `state`, triangulate every HIVE tag corner seen by both
        cameras and store it as that state's reference. Without a `state` the calibration
        state (both audience CELLs up) is learned for each alliance."""
        s = body.get("state")
        if not s:
            return _learn_calibration_state()
        try:
            hs = field.HiveState(str(s.get("alliance", "")), str(s.get("up_cell", "")))
        except ValueError as e:
            raise HTTPException(422, f"state needs a valid alliance and up_cell: {e}") from e
        return _learn_state(hs)

    def _learn_calibration_state() -> dict:
        """Learn every alliance's calibration-state tags that the cameras can see; an
        alliance whose tags are out of view is reported, not an error."""
        results: dict[str, dict] = {}
        errors: dict[str, str] = {}
        for al, up in calibration_state().items():
            try:
                results[f"{al}_{up}"] = _learn_state(field.HiveState(al, up), only_alliance=al)
            except HTTPException as e:
                if e.status_code == 409:
                    raise
                errors[f"{al}_{up}"] = str(e.detail)
        if not results:
            raise HTTPException(422, "; ".join(errors.values()))
        learned_any = [r for r in results.values() if r["learned"]]
        out = {"state": "calibration", "states": results, "errors": errors,
               "learned": bool(learned_any),
               "learned_ids": sorted({i for r in learned_any for i in r["learned_ids"]}),
               "missing_ids": sorted({i for r in results.values() for i in r["missing_ids"]}),
               "max_residual_in": max((r["max_residual_in"] for r in learned_any), default=None),
               "visible_per_camera": next(iter(results.values()))["visible_per_camera"]
               if results else {},
               "up_cell_error_in": None,
               # done once an audience-up state is known (an alliance whose HIVE is out of
               # the cameras' view cannot be learned)
               "complete": any(f"{al}_audience" in st.hive_tags for al in calibration_state())}
        errs = [r["up_cell_error_in"] for r in learned_any if r["up_cell_error_in"] is not None]
        if errs:
            out["up_cell_error_in"] = float(np.mean(errs))
        return out

    def _learn_single_camera(hs, cam: str, tags: dict, visible: dict, intr: dict, ext: dict,
                             want: set, audience_key: str) -> dict:
        """Only one calibrated camera reads the HIVE tags (the other cannot see them): nothing
        can be triangulated, so check each visible tag's single-camera PnP position against
        the computed (CAD) one instead."""
        from . import tagkit
        centers = tagkit._observed_centers(
            {cam: [{"id": i, "corners": c} for i, c in tags.items()]}, {cam: (intr[cam], ext[cam])})
        expected = computed_hive_defs(hs.alliance, hs.up_cell)
        err = {int(i): float(np.linalg.norm(centers[i] - expected[i].mean(axis=0)))
               for i in centers if i in expected}
        from .field_constants import APRILTAG_IDS as _AI
        up_ids = set(_AI[(hs.alliance, hs.up_cell)])
        up_errs = [e for i, e in err.items() if i in up_ids]
        up_err = float(np.mean(up_errs)) if up_errs else None
        complete = audience_key in st.hive_tags or (
            hs.up_cell == "audience" and up_err is not None and up_err < 1.0)
        return {"state": f"{hs.alliance}_{hs.up_cell}", "single_camera": True, "camera": cam,
                "learned": False, "learned_ids": [], "missing_ids": sorted(want - set(visible[cam])),
                "max_residual_in": None, "visible_per_camera": visible,
                "pnp_error_in": {str(i): e for i, e in sorted(err.items())},
                "up_cell_error_in": up_err, "complete": bool(complete),
                "reason": f"only {cam} sees HIVE tags: nothing can be triangulated, the tags were "
                          "checked against the computed positions (single-camera PnP)"}

    def _learn_state(hs, only_alliance: Optional[str] = None) -> dict:
        cams = [c.cam_id for c in st.cfg.sources][:2]
        intr, ext = st.pipeline.calibration()
        if len(cams) < 2 or not all(c in intr and c in ext for c in cams):
            raise HTTPException(409, "calibrate both cameras (intrinsics and extrinsics) first")
        frames = {c: st.pipeline.latest_frame(c) for c in cams}
        if any(f is None for f in frames.values()):
            raise HTTPException(409, "start the pipeline first (frames come from the cameras)")
        ids_ok = set(_hive_ids())
        if only_alliance is not None:
            from .field_constants import APRILTAG_IDS as _AI
            ids_ok &= {i for (al, _c), ids in _AI.items() if al == only_alliance for i in ids}
        dets = {c: {int(d["id"]): d["corners"] for d in calib.detect_apriltags(frames[c].image)
                    if int(d["id"]) in ids_ok} for c in cams}
        visible = {c: sorted(dets[c]) for c in cams}
        common = sorted(set(dets[cams[0]]) & set(dets[cams[1]]))
        from .field_constants import APRILTAG_IDS
        want = {i for (al, _c), ids in APRILTAG_IDS.items() if al == hs.alliance for i in ids}
        audience_key = f"{hs.alliance}_audience"
        if not any(visible.values()):
            # e.g. the far CELL's tags when it is the up one: they face away from cameras on the
            # audience side. Not an error: nothing to learn, and the step can finish when the
            # audience-up state is already known.
            return {"state": f"{hs.alliance}_{hs.up_cell}", "learned": False, "learned_ids": [],
                    "missing_ids": sorted(want), "max_residual_in": None,
                    "visible_per_camera": visible, "up_cell_error_in": None,
                    "reason": f"no HIVE tag of the {hs.up_cell}-up state is visible from these "
                              "cameras (the far CELL's tags face away from the audience side); "
                              "nothing to learn for this state",
                    "complete": audience_key in st.hive_tags}
        readers = [c for c in cams if visible[c]]
        if len(common) < 2 and len(readers) == 1 and len(visible[readers[0]]) >= 2:
            return _learn_single_camera(hs, readers[0], dets[readers[0]], visible, intr, ext,
                                        want, audience_key)
        if len(common) < 2:
            raise HTTPException(
                422, f"only {len(common)} HIVE tag(s) seen by both cameras (cam0 sees "
                f"{visible[cams[0]]}, cam1 sees {visible[cams[1]]}); need at least 2. Check the "
                "HIVE is settled, well lit, and the tags face the cameras.")
        a, b = cams
        learned: dict[str, list] = {}
        worst = 0.0
        for i in common:
            xyz, resid = calib.triangulate(intr[a], ext[a], dets[a][i], intr[b], ext[b], dets[b][i])
            learned[str(i)] = [[float(v) for v in p] for p in np.asarray(xyz).reshape(4, 3)]
            worst = max(worst, float(np.max(resid)))
        key = f"{hs.alliance}_{hs.up_cell}"
        st.hive_tags[key] = learned
        st.save_calib(intr, ext, st.pipeline.stale_extrinsics())
        # sanity check of the whole calibration: the up CELL's tags were triangulated, their
        # positions are also known from the field CAD
        up_err = None
        comp = computed_hive_defs(hs.alliance, hs.up_cell, up_only=True)
        errs = [float(np.mean(np.linalg.norm(np.asarray(learned[str(i)]) - comp[i], axis=1)))
                for i in common if i in comp]
        if errs:
            up_err = float(np.mean(errs))
        return {"state": key, "learned": True, "learned_ids": common,
                "missing_ids": sorted(want - set(common)), "max_residual_in": worst,
                "visible_per_camera": visible, "up_cell_error_in": up_err,
                "complete": audience_key in st.hive_tags}

    @app.get("/api/calib/hive_tags")
    def hive_tags_get():
        from .field_constants import APRILTAG_IDS
        states = {}
        for key, tags in st.hive_tags.items():
            alliance = key.split("_", 1)[0]
            rows = {}
            for (al, cell), ids in APRILTAG_IDS.items():
                if al != alliance:
                    continue
                zs = [np.mean(np.asarray(tags[str(i)], float)[:, 2]) for i in ids if str(i) in tags]
                if zs:
                    rows[f"{al}_{cell}"] = float(np.mean(zs))
            states[key] = {"tags": {i: {"corners_xyz": c,
                                        "center_xyz": np.mean(np.asarray(c, float), axis=0).tolist()}
                                    for i, c in tags.items()},
                           "row_height_in": rows}
        al = st.pipeline.hive_state().alliance
        ready = st.pipeline.hive_tags_ready()
        return {"alliance": al, "states": states, "ready": ready,
                "hive_state_source": st.pipeline.hive_state_source()}

    def _hive_state_advice(roll: dict, tags: dict) -> list[str]:
        """Calibration needs both audience CELLs up (field.CALIBRATION_STATE): say so when the
        visible HIVE tags suggest another state."""
        from .field_constants import APRILTAG_IDS as _AI
        up = calibration_state()
        why: list[str] = []
        clusters: dict[str, set] = {}          # cluster -> signs seen over the cameras
        for per_cam in roll.values():
            for name, v in per_cam.items():
                clusters.setdefault(name, set()).add(int(v.get("sign", 0)))
        for al, cell in up.items():
            wrong = "far" if cell == "audience" else "audience"
            if clusters.get(f"{al}_{cell}") == {-1}:
                why.append(f"the {al} {cell} CELL tags are upside down")
            elif clusters.get(f"{al}_{wrong}") == {1}:
                why.append(f"the {al} {wrong} CELL is up")
        seen = {int(i) for ids in tags.values() for i in ids}
        for al, cell in up.items():
            ids = set(_AI[(al, cell)])
            others_up = [a for a in up if a != al and set(_AI[(a, up[a])]) & seen]
            if others_up and not (ids & seen) and not any(al in w for w in why):
                why.append(f"no {al} {cell} CELL tag is visible while {others_up[0]}'s are")
        if not why:
            return []
        return ["Tip both HIVEs so both audience CELLs are up before calibrating ("
                + "; ".join(why) + ")."]

    @app.get("/api/setup/status")
    def setup_status():
        status = st.pipeline.status()
        running = status["running"]
        cams = status["cameras"]
        # devices the running pipeline holds are reported from its own stream properties;
        # every other index is probed (cached 30 s), whatever the pipeline is doing
        busy: set[int] = set()
        detected: list[dict] = []
        if running:
            for s in st.cfg.sources:
                p = cams.get(s.cam_id, {}).get("props") or {}
                if s.kind == "device" and str(s.target).isdigit():
                    busy.add(int(s.target))
                    if p:
                        detected.append({"index": int(s.target),
                                         "width": int(p.get("width") or 0),
                                         "height": int(p.get("height") or 0),
                                         "fps": float(p.get("fps") or 0.0)})
        detected += [{"index": d["index"], "width": d["width"], "height": d["height"],
                      "fps": d["fps"]} for d in st.free_devices(busy)]
        detected.sort(key=lambda d: d["index"])
        tags = st.pipeline.tags_seen() if running else {}
        roll = st.pipeline.tags_roll() if running else {}
        loaded = status["calibration_loaded"]
        rec: list[str] = []
        sources = st.cfg.sources
        live = [s for s in sources if s.kind != "file"]
        if not st.demo:
            if not detected:
                rec.append("No cameras detected: plug in the cameras (each on its own USB "
                           "port), then press Refresh.")
            if sources and all(s.kind == "file" for s in sources):
                rec.append("The sources are video files; use the Cameras step to pick real "
                           "cameras.")
        if len(sources) < 2:
            rec.append("Only one camera is configured: add a second camera source "
                       "(3D needs two).")
        for s in sources:
            c = cams.get(s.cam_id, {})
            h = int((c.get("props") or {}).get("height") or 0)
            if (running and s.kind == "device" and c.get("is_alive")
                    and c.get("frames_read", 0) > 60 and h >= 1080 and c.get("fps", 0.0) < 59.0):
                rec.append(f"camera {s.cam_id} is at {c['fps']:.0f} fps; move it to its own "
                           "USB port, not a shared hub.")
        if running:
            for cid, n in sorted(st.recent_drops(status).items()):
                rec.append(f"camera {cid} is dropping frames ({n} in the last minute): "
                           "processing too slow; close other programs or lower the preview fps.")
        else:
            for d in detected:
                if d["height"] >= 1080 and 0 < d["fps"] < 59.0:
                    rec.append(f"camera {d['index']} is at {d['fps']:.0f} fps at 1080p; move "
                               "it to its own USB port, not a shared hub.")
        if running:
            rec += _hive_state_advice(roll, tags)
        if not loaded:
            rec.append("No calibration yet: print the tag sheet (Calibration tab) and press "
                       "Auto-calibrate.")
        if running and not loaded:
            for cid, ids in tags.items():
                n = len([i for i in ids if 100 <= i <= 103])
                if n < 2:
                    rec.append(f"{cid} sees {n} of the 4 calibration tags: move the camera or "
                               "the tags so at least 2 are fully visible.")
        if not running and loaded and live:
            rec.append("Calibrated. Press Start to begin tracking shots.")
        return {"cameras_detected": detected, "sources_configured": len(sources) >= 2,
                "calibration_loaded": loaded,
                "calibration_source": status["calibration_source"],
                "intrinsics_default": status["intrinsics_default"],
                "calibration_state": calibration_state(), "tags_seen": tags, "tags_roll": roll,
                "pipeline_running": running, "recommendations": rec}

    @app.post("/api/setup/finish")
    def setup_finish(body: dict = _OPT):
        """The wizard's Done gate: runs the cross-check and refuses (409, plain-language
        reason plus the numbers) while a camera has default or poor lens intrinsics, a pose
        that was not checked against the other camera, or the cross-check error is over
        MAX_FINISH_OOS_IN. A cross-check that is in-sample for a camera never passes silently:
        the 200 carries a warning for it."""
        status = st.pipeline.status()
        if status["demo"]:
            return {"ok": True, "demo": True, "warnings": [],
                    "calibration_source": status["calibration_source"]}
        reasons: list[str] = []
        warnings: list[str] = []
        numbers: dict = {"calibration_source": status["calibration_source"]}
        default_cams = sorted(c for c, v in status["cameras"].items()
                              if v.get("intrinsics_source") == "default")
        numbers["intrinsics_default_cameras"] = default_cams
        if default_cams:
            reasons.append("camera " + ", ".join(default_cams) + " still uses default lens "
                           "intrinsics: run the Lens step (checkerboard) first")
        intr_now, ext_now = st.pipeline.calibration()
        poor = sorted(c for c, v in status["cameras"].items()
                      if v.get("intrinsics_source") == "measured_poor")
        numbers["intrinsics_poor_cameras"] = poor
        for c in poor:
            r = intr_now[c].reprojection_rmse_px if c in intr_now else 0.0
            reasons.append(f"camera {c} lens calibration is poor (RMSE {r:.1f} px): re-run the "
                           "Lens step closer, 1.5-3 ft")
        stale = sorted(c for c, v in status["cameras"].items() if v.get("pair_stale"))
        numbers["pair_stale_cameras"] = stale
        for c in stale:
            reasons.append(f"camera {c} was solved alone after the pair check failed: press "
                           "Auto-calibrate all")
        xc = None
        try:
            xc = _crosscheck()
        except HTTPException as e:
            reasons.append(f"the cross-check could not run: {e.detail}")
        if xc is not None:
            numbers.update(max_error_in=xc["max_error_in"], out_of_sample=xc["out_of_sample"])
            if xc["max_error_in"] > MAX_FINISH_OOS_IN:
                reasons.append(f"the cross-check error is {xc['max_error_in']:.2f} in "
                               f"(limit {MAX_FINISH_OOS_IN:.0f} in): re-measure the tags and "
                               "press Auto-calibrate again")
            # which cameras have an independent check at all?
            per_cam: dict[str, Optional[float]] = {}
            for c in [s.cam_id for s in st.cfg.sources][:2]:
                fr = st.pipeline.latest_frame(c)
                used = set((st.solve_tags.get(c) or {}).get("tags_used", []))
                per_cam[c] = None if fr is None or c not in ext_now else _oos_camera_error(
                    intr_now[c], ext_now[c], fr.image, used)
            numbers["oos_error_in_per_camera"] = per_cam
            for c, v in per_cam.items():
                if v is None:
                    warnings.append(
                        f"camera {c} cross-check is in-sample: tape errors, resolution mismatch "
                        "or a camera swap would not be detected; verify by clicking the 8 corners")
                elif v > MAX_FINISH_OOS_IN:
                    reasons.append(f"camera {c}: a tag that was not used for its solve is "
                                   f"{v:.2f} in off (limit {MAX_FINISH_OOS_IN:.0f} in)")
        if reasons:
            numbers["reasons"] = reasons
            numbers["warnings"] = warnings
            raise Refusal("setup is not finished: " + "; ".join(reasons), numbers)
        out = {"ok": True, **numbers, "warnings": warnings}
        if warnings:
            out["warning"] = warnings[0]
        return out

    @app.post("/api/detector/sample")
    def detector_sample(body: dict = _REQ):
        """Sample a 9x9 HSV patch at a click and widen that ball type's colour range."""
        cam = str(body.get("cam_id", ""))
        _known_cam(cam)
        kind = str(body.get("ball_type", "")).lower()
        if kind not in ("pollen", "nectar"):
            raise HTTPException(422, "ball_type must be 'pollen' or 'nectar'")
        try:
            u, v = float(body["u"]), float(body["v"])
        except (KeyError, TypeError, ValueError) as e:
            raise HTTPException(422, "u and v (image pixels) are required") from e
        fr = st.pipeline.latest_frame(cam)
        if fr is None:
            raise HTTPException(409, f"no frame from {cam}: start the pipeline first")
        h, w = fr.image.shape[:2]
        if body.get("image_width"):
            scale = w / float(body["image_width"])
            u, v = u * scale, v * scale
        if not (0 <= u < w and 0 <= v < h):
            raise HTTPException(422, f"click ({u:.0f}, {v:.0f}) is outside the {w}x{h} frame")
        x, y = int(round(u)), int(round(v))
        patch = fr.image[max(0, y - 4):y + 5, max(0, x - 4):x + 5]
        hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV).reshape(-1, 3)
        sample = [int(round(float(c))) for c in np.median(hsv, axis=0)]
        key = f"{kind}_hsv"
        lo, hi = (list(r) for r in getattr(st.cfg.detector, key))
        new_lo = [max(0, min(lo[0], sample[0] - 8)), max(0, min(lo[1], sample[1] - 40)),
                  max(0, min(lo[2], sample[2] - 40))]
        new_hi = [min(179, max(hi[0], sample[0] + 8)), min(255, max(hi[1], sample[1] + 40)),
                  min(255, max(hi[2], sample[2] + 40))]
        with st.lock:
            new = cfgmod.AppConfig.model_validate(
                cfgmod.merge(st.cfg.to_dict(), {"detector": {key: [new_lo, new_hi]}}))
            st.pipeline.apply_config(new)
            st.cfg = new
            st.save_cfg()
        st.pipeline.set_detector_colors(new.detector.pollen_hsv, new.detector.nectar_hsv)
        return {"ball_type": kind, "sampled_hsv": sample, "range": [new_lo, new_hi]}

    @app.get("/api/field/geometry")
    def field_geometry():
        return field.to_json({st.pipeline.hive_state().alliance:
                              st.pipeline.hive_state().up_cell},
                             field_size_in=st.cfg.field_size_in)

    @app.post("/api/calib/intrinsics/{cam_id}/start")
    def intr_start(cam_id: str, body: dict = _OPT):
        _known_cam(cam_id)
        reader = st.pipeline._readers.get(cam_id)
        if not st.pipeline.running or reader is None:
            raise HTTPException(409, "start the pipeline first (frames come from the capture)")
        old = st.recorders.pop(cam_id, None)
        if old:
            old.stop()
        st.recorders[cam_id] = _Recorder(reader)
        return {"ok": True, "recording": True}

    @app.post("/api/calib/intrinsics/{cam_id}/stop")
    def intr_stop(cam_id: str, body: dict = _OPT):
        rec = st.recorders.pop(cam_id, None)
        if rec is None:
            raise HTTPException(409, "not recording")
        frames = rec.stop()
        pattern = tuple(body.get("pattern", (9, 6)))
        square = float(body.get("square_in", 1.0))
        try:
            intr = calib.calibrate_intrinsics(frames, pattern, square, cam_id)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        used = 0
        for f in frames:
            g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
            used += bool(cv2.findChessboardCorners(g, pattern)[0])
        old_i, old_e = st.pipeline.calibration()
        new_i = {**old_i, cam_id: intr}
        # extrinsics solved with the old intrinsics no longer match: flag them stale
        stale = st.pipeline.stale_extrinsics() | ({cam_id} if cam_id in old_e else set())
        rmse = float(intr.reprojection_rmse_px)
        source = "measured_poor" if rmse > LENS_POOR_RMSE_PX else "measured"
        st.save_calib(new_i, old_e, stale, measured={cam_id: source})
        out = {"reprojection_rmse_px": rmse, "frames_used": used, "intrinsics_source": source}
        if source == "measured_poor":
            out["warning"] = (f"lens RMSE {rmse:.1f} px is over {LENS_POOR_RMSE_PX:.0f} px: "
                              "saved as poor; re-run the Lens step closer, 1.5-3 ft from the "
                              "camera (setup cannot finish until you do)")
        elif rmse >= LENS_OK_RMSE_PX:
            out["warning"] = (f"lens RMSE {rmse:.1f} px is mediocre (under 1 px is good): "
                              "consider re-running the Lens step closer, 1.5-3 ft")
        return out

    @app.post("/api/calib/extrinsics/{cam_id}")
    def extr_solve(cam_id: str, body: dict = _REQ):
        _known_cam(cam_id)
        old_i, old_e = st.pipeline.calibration()
        if cam_id not in old_i:
            raise HTTPException(409, f"no intrinsics for {cam_id}; calibrate intrinsics first")
        ref = calib_targets.field_reference_points()
        lookup = {n.lower(): p for n, p in ref}
        pts = body.get("points") or []
        scale = 1.0
        if body.get("image_width"):
            fr = st.pipeline.latest_frame(cam_id)
            w = fr.image.shape[1] if fr is not None else old_i[cam_id].width
            scale = w / float(body["image_width"])
        img, fld, names = [], [], []
        for p in pts:
            n = str(p.get("name", ""))
            xyz = lookup.get(n.lower())
            if xyz is None:
                raise HTTPException(422, f"unknown reference point name {n!r}")
            img.append((float(p["u"]) * scale, float(p["v"]) * scale))
            fld.append(xyz)
            names.append(n)
        try:
            ext = calib.solve_extrinsics_from_points(
                old_i[cam_id], np.array(img), np.array(fld), cam_id)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        rep = calib.reprojection_report(old_i[cam_id], ext, np.array(img), np.array(fld))
        rms_px = float(np.sqrt(np.mean(np.square(rep["per_point_px"]))))
        record = {"source": "clicks", "tags_used": []}
        was_default = st.pipeline.intrinsics_sources().get(cam_id) == "default"
        fr = st.pipeline.latest_frame(cam_id)
        oos, stale_other = _gate_extrinsics(
            cam_id, old_i[cam_id], ext, rms_px, record, None if fr is None else fr.image,
            force_single=bool(body.get("force_single")))
        st.clicks[cam_id] = [{"name": n, "u": float(u), "v": float(v)}
                             for n, (u, v) in zip(names, img, strict=True)]
        st.solve_tags[cam_id] = record
        st.save_calib(old_i, {**old_e, cam_id: ext},
                      st.pipeline.stale_extrinsics() - {cam_id})
        st.pipeline.set_pair_stale(cam_id, False)
        if stale_other:
            st.pipeline.set_pair_stale(stale_other, True)
        return {"rmse_in": ext.rmse_in, "fit_residual_in": ext.rmse_in, "oos_error_in": oos,
                "pair_stale": [stale_other] if stale_other else [],
                "reprojection_px": rms_px, "intrinsics_default": was_default,
                "per_point": [{"name": n, "err_px": e}
                              for n, e in zip(names, rep["per_point_px"], strict=True)]}

    # ------------------------------------------------------------- websocket
    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        st.clients.add(ws)
        try:
            await ws.send_json(st.status_msg())
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception:  # noqa: BLE001
            pass
        finally:
            st.clients.discard(ws)

    # ----------------------------------------------------------------- static
    @app.exception_handler(Refusal)
    async def _refusal(_: Request, exc: Refusal):
        return JSONResponse({**exc.extra, "detail": exc.detail, "refused": True},
                            status_code=exc.status)

    @app.exception_handler(ValueError)
    async def _value_error(_: Request, exc: ValueError):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    if (UI_DIR / "vendor").is_dir():
        app.mount("/vendor", StaticFiles(directory=UI_DIR / "vendor"), name="vendor")
    class _ClipFiles(StaticFiles):
        """/clips from the current data dir (it changes while the demo runs)."""

        def lookup_path(self, path: str):
            root = os.path.realpath(st.data_dir / "clips")
            if path.startswith(("/", "\\")):
                return "", None
            full = os.path.realpath(os.path.join(root, path))
            try:
                if os.path.commonpath([full, root]) != root:
                    return "", None
                return full, os.stat(full)
            except (ValueError, FileNotFoundError, NotADirectoryError):
                return "", None

    app.mount("/clips", _ClipFiles(directory=st.data_dir / "clips", check_dir=False),
              name="clips")
    app.mount("/", StaticFiles(directory=UI_DIR, html=True, check_dir=False), name="ui")
    return app


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hiveshot", description="HiveShotTracker server")
    p.add_argument("--config", default=None, help="config json (default data/config.json)")
    p.add_argument("--data-dir", default=None,
                   help=f"data directory (default {cfgmod.default_data_dir()})")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--source", action="append", default=[], metavar="CAM_ID=PATH",
                   help="override sources with video files (repeatable)")
    p.add_argument("--autostart", action="store_true", help="start the pipeline on launch")
    p.add_argument("--open-browser", action="store_true",
                   help="open the dashboard in the browser at start (default on for the "
                        "packaged exe)")
    p.add_argument("--no-browser", action="store_true",
                   help="do not open the browser (also for the packaged exe)")
    p.add_argument("--demo", action="store_true",
                   help="run the bundled demo footage in <data-dir>/demo (nothing external, "
                        "your config and sessions are not touched)")
    return p


def wants_browser(a: argparse.Namespace, frozen: bool) -> bool:
    """Open the dashboard at start: on for --open-browser, --demo and the packaged exe;
    --no-browser always wins."""
    return (a.open_browser or a.demo or frozen) and not a.no_browser


def main(argv: Optional[list[str]] = None) -> None:
    import uvicorn
    a = build_parser().parse_args(argv)
    overrides = None
    if a.source:
        srcs = []
        for s in a.source:
            cam, _, path = s.partition("=")
            if not path:
                raise SystemExit(f"--source expects CAM_ID=PATH, got {s!r}")
            srcs.append({"cam_id": cam, "kind": "file", "target": path,
                         "loop": False, "realtime": True})
        overrides = {"sources": srcs}
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    app = create_app(a.config, a.data_dir, overrides=overrides, autostart=a.autostart,
                     demo=a.demo)
    if wants_browser(a, bool(getattr(sys, "frozen", False))):
        threading.Timer(1.5, lambda: webbrowser.open(f"http://{a.host}:{a.port}/")).start()
    uvicorn.run(app, host=a.host, port=a.port, log_level="info")


if __name__ == "__main__":
    main()

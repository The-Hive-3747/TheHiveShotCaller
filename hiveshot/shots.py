"""Turn 3D tracks into Shot records: classification, bursts, tip detection."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Callable, Optional

import numpy as np

from . import physics
from .field import (
    HiveState,
    cell_opening_plane,
    cell_opening_polygon,
    point_inside_cell,
    segment_crosses_opening,
)
from .field_constants import MAX_BALLS_HELD, NECTAR_DIAMETER, POLLEN_DIAMETER
from .models import BallType, DragFit, Shot, ShotResult, TipEvent, Track3D

Vec = tuple[float, float, float]
CrossFn = Callable[[Vec, Vec, float], Optional[tuple[float, Any]]]
InsideFn = Callable[[Vec], bool]
PlaneMissFn = Callable[[Vec, Vec, float], bool]

# MISS needs evidence (see classify). Lowest z of the up-CELL opening polygon, used when the
# caller supplies no geometry (the two alliances/cells share the same heights).
DEFAULT_OPENING_BOTTOM_Z = float(cell_opening_polygon("red", "audience", HiveState())[:, 2].min())
NOTE_LOST_NEAR_OPENING = "track lost near the opening"
NOTE_LOST_MIDAIR = "track lost mid-air"
NOTE_LEFT_WALL = "track left the CELL through a wall (synthetic?)"
DROPPED_NOTE_RE = re.compile(r"frames dropped during flight \((\d+)\)")


def _default_radii() -> dict[BallType, float]:
    return {
        BallType.POLLEN: POLLEN_DIAMETER / 2,
        BallType.NECTAR: NECTAR_DIAMETER / 2,
        BallType.UNKNOWN: POLLEN_DIAMETER / 2,
    }


@dataclass
class ShotClassifierConfig:
    burst_gap_s: float = 1.5
    ball_radius_in: dict[BallType, float] = field(default_factory=_default_radii)
    settle_time_s: float = 0.75
    min_points: int = 4
    # Geometry used to decide whether a track without an opening crossing is a real miss.
    opening_bottom_z: Optional[float] = None      # lowest z of the opening polygon
    opening_center: Optional[Vec] = None          # opening centre (x, y, z)
    plane_miss: Optional[PlaneMissFn] = None      # segment clearly crosses the plane outside it
    # outward crossing of the opening plane inside the opening polygon; with it set, only
    # such an exit is a BOUNCE_OUT (None = legacy: leaving the CELL box by any face is)
    exits_opening: Optional[CrossFn] = None
    floor_z_in: float = 10.0                      # a track ending at or below this has landed
    near_opening_xy_in: float = 24.0              # "lost near the opening" horizontal radius

    def radius_for(self, ball_type: BallType) -> float:
        return self.ball_radius_in.get(ball_type, POLLEN_DIAMETER / 2)


@dataclass(frozen=True)
class Classification:
    result: ShotResult
    entry_t: Optional[float] = None
    note: str = ""


def _no_entry(pts, cfg: ShotClassifierConfig, radius: float) -> Classification:
    """Decide MISS vs UNKNOWN for a track that never entered the opening. MISS needs
    evidence that the ball really came down without entering: it clearly crossed the
    opening plane outside the opening, descended below the opening's lower edge after its
    apex, or landed. A track that just stops (mid-air) is UNKNOWN."""
    bottom = cfg.opening_bottom_z if cfg.opening_bottom_z is not None         else DEFAULT_OPENING_BOTTOM_Z
    last = pts[-1]
    if cfg.plane_miss is not None:
        for a, b in zip(pts, pts[1:], strict=False):
            if cfg.plane_miss((a.x, a.y, a.z), (b.x, b.y, b.z), radius):
                return Classification(ShotResult.MISS)
    apex_i = max(range(len(pts)), key=lambda i: pts[i].z)
    after_apex = pts[apex_i + 1:]
    if any(p.z < bottom for p in after_apex):
        return Classification(ShotResult.MISS)
    if after_apex and last.z <= cfg.floor_z_in:
        return Classification(ShotResult.MISS)
    if cfg.opening_center is not None and last.z > bottom and             math.hypot(last.x - cfg.opening_center[0],
                       last.y - cfg.opening_center[1]) <= cfg.near_opening_xy_in:
        return Classification(ShotResult.UNKNOWN, None, NOTE_LOST_NEAR_OPENING)
    return Classification(ShotResult.UNKNOWN, None, NOTE_LOST_MIDAIR)


# A track crossing the opening plane this far (ball radius + margin) outside the opening
# polygon is a clear miss.
PLANE_MISS_MARGIN_IN = 3.0


def opening_classifier(alliance: str, which: str, state: HiveState, **cfg_kw
                       ) -> tuple[ShotClassifierConfig, CrossFn, InsideFn]:
    """(config with the opening geometry, crosses_opening, inside_cell) for the `which`
    CELL of `alliance` in HIVE `state`; extra keywords go to ShotClassifierConfig."""
    centre, normal = cell_opening_plane(alliance, which, state)
    cfg = ShotClassifierConfig(
        opening_bottom_z=float(cell_opening_polygon(alliance, which, state)[:, 2].min()),
        opening_center=(float(centre[0]), float(centre[1]), float(centre[2])), **cfg_kw)

    def crosses(p0, p1, r):
        return segment_crosses_opening(p0, p1, alliance, which, state, r)

    def inside(p):
        return point_inside_cell(p, alliance, which, state)

    def plane_miss(p0, p1, r):
        """Inward crossing of the opening plane clearly outside the opening."""
        d0 = float(np.dot(np.asarray(p0, float) - centre, normal))
        d1 = float(np.dot(np.asarray(p1, float) - centre, normal))
        if not (d0 > 0.0 >= d1):
            return False
        return segment_crosses_opening(p0, p1, alliance, which, state,
                                       -(r + PLANE_MISS_MARGIN_IN)) is None

    def exits(p0, p1, r):
        """Outward crossing of the opening plane inside the (slightly widened) opening."""
        return segment_crosses_opening(p1, p0, alliance, which, state, -PLANE_MISS_MARGIN_IN)

    cfg.plane_miss = plane_miss
    cfg.exits_opening = exits
    return cfg, crosses, inside


def classify(track: Track3D, crosses_opening: CrossFn, inside_cell: InsideFn,
             config: Optional[ShotClassifierConfig] = None) -> Classification:
    """Classify one track. `crosses_opening(p0, p1, radius)` returns
    (fraction in [0,1] along the segment, point) for an inward crossing, else
    None. `inside_cell(p)` tests the CELL box. A track that never crosses is a MISS only
    with evidence (see `_no_entry`), otherwise UNKNOWN with an explanatory note."""
    cfg = config or ShotClassifierConfig()
    pts = track.points
    if len(pts) < cfg.min_points:
        return Classification(ShotResult.UNKNOWN)
    radius = cfg.radius_for(track.ball_type)

    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        hit = crosses_opening((a.x, a.y, a.z), (b.x, b.y, b.z), radius)
        if hit is None:
            continue
        entry_t = a.t + float(hit[0]) * (b.t - a.t)
        for j in range(i + 1, len(pts)):
            q = pts[j]
            if q.t - entry_t > cfg.settle_time_s:
                break  # stayed inside long enough: settled
            if not inside_cell((q.x, q.y, q.z)):
                if cfg.exits_opening is None or any(
                        cfg.exits_opening((pts[k].x, pts[k].y, pts[k].z),
                                          (pts[k + 1].x, pts[k + 1].y, pts[k + 1].z), radius)
                        for k in range(i + 1, j)):
                    return Classification(ShotResult.BOUNCE_OUT, entry_t)
                # left the box through a wall or the floor: not a physical bounce-out
                return Classification(ShotResult.UNKNOWN, entry_t, NOTE_LEFT_WALL)
        return Classification(ShotResult.MADE, entry_t)
    return _no_entry(pts, cfg, radius)


def classify_track(track: Track3D, crosses_opening: CrossFn, inside_cell: InsideFn,
                   config: Optional[ShotClassifierConfig] = None
                   ) -> tuple[ShotResult, Optional[float]]:
    """(result, entry time) of `classify`."""
    c = classify(track, crosses_opening, inside_cell, config)
    return c.result, c.entry_t


def _azimuth_deg(track: Track3D) -> Optional[float]:
    p0, p1 = track.points[0], track.points[-1]
    dx, dy = p1.x - p0.x, p1.y - p0.y
    if math.hypot(dx, dy) < 1e-9:
        return None
    return math.degrees(math.atan2(dy, dx))


def build_shot(track: Track3D, session_id: str, shot_id: int,
               classify_fns: tuple[CrossFn, InsideFn], ball_type: BallType,
               config: Optional[ShotClassifierConfig] = None) -> Shot:
    """Build a Shot from a track. Burst fields are placeholders (0, 0) until
    assign_bursts is called. A failed parabola fit leaves the fits as None."""
    crosses, inside = classify_fns
    cls = classify(track, crosses, inside, config)
    result = cls.result
    notes = cls.note
    parabola = None
    drag: Optional[DragFit] = None
    try:
        parabola = physics.fit_parabola(track)
    except ValueError as e:
        notes = (notes + "; " if notes else "") + f"parabola fit failed: {e}"
    if parabola is not None:
        try:
            drag = physics.fit_drag(track)
        except Exception as e:  # optional fit; never fail the shot
            notes = (notes + "; " if notes else "") + f"drag fit failed: {e}"
    first = track.points[0] if track.points else None
    return Shot(
        shot_id=shot_id, session_id=session_id,
        t_launch=first.t if first else 0.0,
        burst_id=0, burst_index=0, ball_type=ball_type, result=result,
        exit_speed_ips=parabola.exit_speed_ips if parabola else None,
        launch_angle_deg=parabola.launch_angle_deg if parabola else None,
        launch_azimuth_deg=_azimuth_deg(track) if first else None,
        launch_point=(first.x, first.y, first.z) if first else None,
        apex_z_in=physics.apex(parabola) if parabola else None,
        parabola=parabola, drag=drag, track=track, notes=notes,
    )


def dropped_during_flight(notes: str) -> int:
    """Frames lost by the cameras during the shot, parsed from the shot notes."""
    return sum(int(m) for m in DROPPED_NOTE_RE.findall(notes or ""))


def dropped_note(n: int) -> str:
    return f"frames dropped during flight ({n})"


def wall_iso(session_start: Optional[float], t_launch: float) -> Optional[str]:
    """ISO 8601 wall-clock time of a launch: session start (epoch s) + t_launch, or None
    when the session start is unknown."""
    if session_start is None:
        return None
    ts = float(session_start) + float(t_launch)
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="milliseconds")


def summarize(shot: Shot, session_start: Optional[float] = None) -> dict:
    """store.shot_summary plus the additive `dropped_during_flight` and `t_launch_wall`."""
    from .store import shot_summary
    return annotate(shot_summary(shot), shot, session_start)


def annotate(d: dict, shot: Shot, session_start: Optional[float] = None) -> dict:
    d["dropped_during_flight"] = dropped_during_flight(shot.notes)
    d["t_launch_wall"] = wall_iso(session_start, shot.t_launch)
    return d


_BURST_TAG_RE = re.compile(r"(?:;\s*)?burst exceeds \d+ balls \(index \d+\)")


def assign_bursts(shots: list[Shot], gap_s: float = 1.5) -> list[Shot]:
    """Sort by launch time; a gap > gap_s starts a new burst. burst_index is
    1-based and keeps counting past MAX_BALLS_HELD, with a note recorded."""
    ordered = sorted(shots, key=lambda s: s.t_launch)
    out: list[Shot] = []
    burst_id, idx, last_t = 0, 0, None
    for s in ordered:
        if last_t is None or s.t_launch - last_t > gap_s:
            burst_id += 1
            idx = 0
        idx += 1
        last_t = s.t_launch
        notes = _BURST_TAG_RE.sub("", s.notes or "").strip("; ").strip()
        if idx > MAX_BALLS_HELD:
            tag = f"burst exceeds {MAX_BALLS_HELD} balls (index {idx})"
            notes = (notes + "; " if notes else "") + tag
        out.append(replace(s, burst_id=burst_id, burst_index=idx, notes=notes))
    return out


def detect_tip(shots_in_order: list[Shot],
               hive_state_observer: Callable[[float], Any],
               alliance: str = "red", session_id: Optional[str] = None,
               settle_s: float = 1.0) -> list[TipEvent]:
    """Emit a TipEvent when the observed up_cell changes across a MADE shot.
    The state is observed at the shot's launch and `settle_s` after the end of
    its track (or of its launch if there is no track)."""
    events: list[TipEvent] = []
    for shot in shots_in_order:
        if shot.result != ShotResult.MADE:
            continue
        t_end = shot.track.points[-1].t if shot.track and shot.track.points else shot.t_launch
        before = hive_state_observer(shot.t_launch).up_cell
        t_after = t_end + settle_s
        after = hive_state_observer(t_after).up_cell
        if before != after:
            events.append(TipEvent(t=t_after, session_id=session_id or shot.session_id,
                                   alliance=alliance, new_up_cell=after,
                                   caused_by_shot_id=shot.shot_id))
    return events

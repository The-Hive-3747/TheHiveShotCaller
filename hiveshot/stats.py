"""Session statistics and CSV export."""

from __future__ import annotations

import csv
import dataclasses
from pathlib import Path
from typing import Iterable, Optional

from .models import SessionStats, Shot, ShotResult, TipEvent

IPS_TO_MPS = 0.0254
OVERFLOW_KEY = 5  # burst_index > 4


def _order_key(burst_index: int) -> int:
    return min(max(burst_index, 1), OVERFLOW_KEY)


def _mean(vals: list[float]) -> Optional[float]:
    return sum(vals) / len(vals) if vals else None


def compute_stats(shots: Iterable[Shot], tips: Iterable[TipEvent], session_id: str) -> SessionStats:
    shots = list(shots)
    n = len(shots)
    counts = {r: sum(1 for s in shots if s.result == r) for r in ShotResult}
    fail = {k: 0 for k in range(1, OVERFLOW_KEY + 1)}
    bounce = {k: 0 for k in range(1, OVERFLOW_KEY + 1)}
    by_type: dict[str, dict[str, int]] = {}
    for s in shots:
        d = by_type.setdefault(s.ball_type.value, {
            "made": 0, "bounce_out": 0, "miss": 0, "unknown": 0, "shots": 0})
        d[s.result.value] += 1
        d["shots"] += 1
        if s.result != ShotResult.MADE:
            fail[_order_key(s.burst_index)] += 1
        if s.result == ShotResult.BOUNCE_OUT:
            bounce[_order_key(s.burst_index)] += 1
    speeds = [s.exit_speed_ips for s in shots if s.exit_speed_ips is not None]
    angles = [s.launch_angle_deg for s in shots if s.launch_angle_deg is not None]
    return SessionStats(
        session_id=session_id, shots=n,
        made=counts[ShotResult.MADE], bounce_out=counts[ShotResult.BOUNCE_OUT],
        miss=counts[ShotResult.MISS], unknown=counts[ShotResult.UNKNOWN],
        make_rate=counts[ShotResult.MADE] / n if n else 0.0,
        by_ball_type=by_type, failure_order_hist=fail, bounce_out_order_hist=bounce,
        tips=len(list(tips)),
        mean_exit_speed_ips=_mean(speeds), mean_launch_angle_deg=_mean(angles),
    )


def stats_to_dict(stats: SessionStats) -> dict:
    """JSON-safe dict (int histogram keys become strings)."""
    d = dataclasses.asdict(stats)
    d["failure_order_hist"] = {str(k): v for k, v in stats.failure_order_hist.items()}
    d["bounce_out_order_hist"] = {str(k): v for k, v in stats.bounce_out_order_hist.items()}
    return d


CSV_FIELDS = [
    "shot_id", "session_id", "t_launch", "burst_id", "burst_index", "ball_type", "result",
    "exit_speed_ips", "exit_speed_mps", "launch_angle_deg", "launch_azimuth_deg",
    "parabola_a", "parabola_b", "parabola_c", "apex_z_in", "notes", "t_launch_wall",
]


def _blank(v):
    return "" if v is None else v


_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _safe_text(value):
    """Neutralize spreadsheet formula injection: text starting with = + - @ gets a leading
    single quote. Numbers are written as numbers and are never touched."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def shots_to_csv(shots: Iterable[Shot], path, session_start: Optional[float] = None) -> None:
    """Write the shots as CSV. `session_start` (epoch seconds) enables `t_launch_wall`
    (ISO 8601 = session start + t_launch); it is blank when the start is unknown."""
    from .shots import wall_iso
    with open(Path(path), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for s in shots:
            p = s.parabola
            row = {
                "shot_id": s.shot_id, "session_id": s.session_id, "t_launch": s.t_launch,
                "burst_id": s.burst_id, "burst_index": s.burst_index,
                "ball_type": s.ball_type.value, "result": s.result.value,
                "exit_speed_ips": _blank(s.exit_speed_ips),
                "exit_speed_mps": "" if s.exit_speed_ips is None else s.exit_speed_ips * IPS_TO_MPS,
                "launch_angle_deg": _blank(s.launch_angle_deg),
                "launch_azimuth_deg": _blank(s.launch_azimuth_deg),
                "parabola_a": "" if p is None else p.a,
                "parabola_b": "" if p is None else p.b,
                "parabola_c": "" if p is None else p.c,
                "apex_z_in": _blank(s.apex_z_in),
                "notes": s.notes,
                "t_launch_wall": wall_iso(session_start, s.t_launch) or "",
            }
            w.writerow({k: _safe_text(v) for k, v in row.items()})

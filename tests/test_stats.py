import csv
import json

import pytest

from hiveshot.models import BallType, ParabolaFit, Shot, ShotResult, TipEvent
from hiveshot.stats import compute_stats, shots_to_csv, stats_to_dict

M, B, X, U = ShotResult.MADE, ShotResult.BOUNCE_OUT, ShotResult.MISS, ShotResult.UNKNOWN


def shot(i, result, idx, ball=BallType.POLLEN, speed=300.0, angle=45.0):
    par = ParabolaFit(-0.01, 0.9, 12.0, 0.1, angle, speed) if speed is not None else None
    return Shot(i, "s", float(i), 1, idx, ball, result, speed,
                angle if speed is not None else None, 10.0, (0, 0, 12.0), 50.0, par,
                None, None)


SHOTS = [
    shot(1, M, 1), shot(2, B, 2), shot(3, X, 3, BallType.NECTAR),
    shot(4, B, 4), shot(5, X, 5, BallType.NECTAR), shot(6, U, 6, speed=None),
    shot(7, M, 1, BallType.NECTAR, speed=200.0, angle=35.0),
]


def test_counts_and_rate():
    st = compute_stats(SHOTS, [], "s")
    assert (st.shots, st.made, st.bounce_out, st.miss, st.unknown) == (7, 2, 2, 2, 1)
    assert st.make_rate == pytest.approx(2 / 7)


def test_histograms():
    st = compute_stats(SHOTS, [], "s")
    assert st.failure_order_hist == {1: 0, 2: 1, 3: 1, 4: 1, 5: 2}
    assert st.bounce_out_order_hist == {1: 0, 2: 1, 3: 0, 4: 1, 5: 0}


def test_by_ball_type():
    st = compute_stats(SHOTS, [], "s")
    assert st.by_ball_type["pollen"] == {
        "made": 1, "bounce_out": 2, "miss": 0, "unknown": 1, "shots": 4}
    assert st.by_ball_type["nectar"] == {
        "made": 1, "bounce_out": 0, "miss": 2, "unknown": 0, "shots": 3}


def test_means_skip_missing_and_tips_counted():
    tips = [TipEvent(1.0, "s", "red", "far", 2)]
    st = compute_stats(SHOTS, tips, "s")
    assert st.tips == 1
    assert st.mean_exit_speed_ips == pytest.approx((300 * 5 + 200) / 6)
    assert st.mean_launch_angle_deg == pytest.approx((45 * 5 + 35) / 6)


def test_empty():
    st = compute_stats([], [], "s")
    assert st.make_rate == 0 and st.shots == 0
    assert st.mean_exit_speed_ips is None and st.mean_launch_angle_deg is None


def test_stats_to_dict_json_safe():
    d = stats_to_dict(compute_stats(SHOTS, [], "s"))
    back = json.loads(json.dumps(d))
    assert back["failure_order_hist"]["5"] == 2
    assert back["made"] == 2


def test_csv(tmp_path):
    p = tmp_path / "shots.csv"
    shots_to_csv(SHOTS, p)
    with open(p, newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len(SHOTS)
    r = rows[0]
    for col in ("parabola_a", "parabola_b", "parabola_c", "exit_speed_ips", "exit_speed_mps",
                "launch_angle_deg", "result", "burst_id", "burst_index", "ball_type",
                "t_launch", "apex_z_in"):
        assert col in r
    assert float(r["exit_speed_mps"]) == pytest.approx(300.0 * 0.0254)
    assert r["result"] == "made" and r["ball_type"] == "pollen"
    assert rows[5]["exit_speed_ips"] == "" and rows[5]["parabola_a"] == ""


def test_csv_neutralizes_formula_injection(tmp_path):
    from dataclasses import replace
    nasty = ["=cmd|' /C calc'!A0", "+1+1", "-2+3", "@SUM(A1)", "plain note", "", "a=b"]
    shots = [replace(SHOTS[0], shot_id=i, notes=n) for i, n in enumerate(nasty, 1)]
    shots[0] = replace(shots[0], session_id="=evil")
    p = tmp_path / "x.csv"
    shots_to_csv(shots, p)
    with open(p, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert [r["notes"] for r in rows] == ["'" + nasty[0], "'" + nasty[1], "'" + nasty[2],
                                          "'" + nasty[3], "plain note", "", "a=b"]
    assert rows[0]["session_id"] == "'=evil"
    for r in rows:
        assert not r["notes"].startswith(("=", "+", "-", "@"))
    # numbers (a negative azimuth, say) are numbers, not text, and are left alone
    neg = replace(SHOTS[0], launch_azimuth_deg=-45.0)
    shots_to_csv([neg], p)
    with open(p, newline="", encoding="utf-8") as f:
        assert next(csv.DictReader(f))["launch_azimuth_deg"] == "-45.0"


def test_csv_t_launch_wall(tmp_path):
    from datetime import datetime
    p = tmp_path / "w.csv"
    shots_to_csv(SHOTS[:2], p)                          # no session start: blank column
    with open(p, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert "t_launch_wall" in rows[0] and [r["t_launch_wall"] for r in rows] == ["", ""]
    start = 1_700_000_000.0
    shots_to_csv(SHOTS[:2], p, session_start=start)
    with open(p, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r, s in zip(rows, SHOTS[:2], strict=True):
        dt = datetime.fromisoformat(r["t_launch_wall"])
        assert dt.tzinfo is not None
        assert dt.timestamp() == pytest.approx(start + s.t_launch, abs=0.001)

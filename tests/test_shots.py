from types import SimpleNamespace

import pytest

from hiveshot import shots as S
from hiveshot.field_constants import MAX_BALLS_HELD
from hiveshot.models import BallType, Point3D, Shot, ShotResult, Track3D


def make_track(n=30, dt=1 / 60, ball=BallType.POLLEN):
    pts = []
    for i in range(n):
        t = i * dt
        pts.append(Point3D(t=t, x=200.0 * t, y=100.0 * t,
                           z=12 + 300 * t - 0.5 * 386.09 * t * t))
    return Track3D(1, pts, ball)


def stub_cross(track, idx, frac=0.5):
    p0 = track.points[idx]

    def crosses(a, b, r):
        if a == (p0.x, p0.y, p0.z):
            return frac, b
        return None
    return crosses


def inside_from(track, first_idx, last_idx=None):
    ok = {(p.x, p.y, p.z) for p in track.points[first_idx:last_idx]}
    return lambda p: tuple(p) in ok


def test_made_when_inside_thereafter():
    tr = make_track()
    res, t = S.classify_track(tr, stub_cross(tr, 10), inside_from(tr, 11))
    assert res == ShotResult.MADE
    assert tr.points[10].t < t < tr.points[11].t


def test_bounce_out_when_leaves_cell():
    tr = make_track()
    res, t = S.classify_track(tr, stub_cross(tr, 10), inside_from(tr, 11, 16))
    assert res == ShotResult.BOUNCE_OUT
    assert t is not None


def test_miss_without_crossing():
    # a ball that went up, came down and landed without ever crossing: MISS
    pts = []
    for i in range(110):
        t = i / 60
        pts.append(Point3D(t=t, x=100.0 * t, y=50.0 * t, z=max(0.0, 12 + 300 * t - 0.5 * 386.09 * t * t)))
    res, t = S.classify_track(Track3D(1, pts, BallType.POLLEN), lambda a, b, r: None,
                              lambda p: False)
    assert res == ShotResult.MISS and t is None


def test_unknown_with_three_points():
    tr = make_track(n=3)
    res, t = S.classify_track(tr, lambda a, b, r: (0.5, b), lambda p: True)
    assert res == ShotResult.UNKNOWN and t is None


def test_leaving_after_settle_time_still_made():
    tr = make_track(n=90)
    cfg = S.ShotClassifierConfig(settle_time_s=0.5)
    # Inside for frames 11..59 (~0.8 s), outside afterwards.
    res, _ = S.classify_track(tr, stub_cross(tr, 10), inside_from(tr, 11, 60), cfg)
    assert res == ShotResult.MADE


def test_radius_passed_by_ball_type():
    seen = []

    def crosses(a, b, r):
        seen.append(r)
        return None

    S.classify_track(make_track(ball=BallType.NECTAR), crosses, lambda p: True)
    assert seen and seen[0] == pytest.approx(1.8)


def test_build_shot_fields():
    tr = make_track()
    fns = (stub_cross(tr, 10), inside_from(tr, 11))
    shot = S.build_shot(tr, "sess", 7, fns, BallType.POLLEN)
    assert shot.result == ShotResult.MADE
    assert shot.shot_id == 7 and shot.session_id == "sess"
    assert shot.t_launch == 0.0
    assert shot.launch_point == (0.0, 0.0, 12.0)
    assert shot.exit_speed_ips == pytest.approx((200**2 + 100**2 + 300**2) ** 0.5, rel=0.01)
    assert shot.launch_angle_deg == pytest.approx(53.3, abs=1.0)
    assert shot.launch_azimuth_deg == pytest.approx(26.565, abs=0.1)
    assert shot.apex_z_in == pytest.approx(12 + 300**2 / (2 * 386.09), rel=0.02)
    assert shot.parabola is not None


def test_build_shot_short_track_has_no_fits():
    tr = make_track(n=3)
    shot = S.build_shot(tr, "s", 1, (lambda a, b, r: None, lambda p: False), BallType.POLLEN)
    assert shot.result == ShotResult.UNKNOWN
    assert shot.parabola is None and shot.drag is None and "failed" in shot.notes


def blank_shot(i, t, result=ShotResult.MADE):
    return Shot(i, "s", t, 0, 0, BallType.POLLEN, result, 300.0, 45.0, 0.0, None, None,
                None, None, None)


def test_assign_bursts():
    shots = [blank_shot(i, t) for i, t in enumerate([5.5, 0, 0.4, 0.8, 1.2, 5.0])]
    out = S.assign_bursts(shots, 1.5)
    assert [s.t_launch for s in out] == [0, 0.4, 0.8, 1.2, 5.0, 5.5]
    assert [s.burst_id for s in out] == [1, 1, 1, 1, 2, 2]
    assert [s.burst_index for s in out] == [1, 2, 3, 4, 1, 2]


def test_assign_bursts_overflow_notes():
    out = S.assign_bursts([blank_shot(i, 0.2 * i) for i in range(6)], 1.5)
    assert [s.burst_index for s in out] == [1, 2, 3, 4, 5, 6]
    assert all(s.notes == "" for s in out[:MAX_BALLS_HELD])
    assert all("burst" in s.notes for s in out[MAX_BALLS_HELD:])


def test_detect_tip_one_event_after_shot_three():
    shots = [blank_shot(i, 10.0 * i) for i in range(1, 6)]  # ids 1..5, t=10..50

    def observer(t):
        # Shots have no track, so the after-time is t_launch + 1.0 s. The state
        # flips at 30.5: after shot 3's launch (30.0) and before its after-time.
        return SimpleNamespace(up_cell="audience" if t < 30.5 else "far")

    events = S.detect_tip(shots, observer, alliance="red", session_id="s")
    assert len(events) == 1
    e = events[0]
    assert e.caused_by_shot_id == 3 and e.new_up_cell == "far" and e.alliance == "red"


def test_detect_tip_ignores_non_made():
    shots = [blank_shot(1, 10.0, ShotResult.MISS)]

    def observer(t):
        return SimpleNamespace(up_cell="audience" if t < 10.5 else "far")

    assert S.detect_tip(shots, observer) == []


def test_assign_bursts_is_idempotent():
    shots = [blank_shot(i, 0.2 * i) for i in range(7)]
    once = S.assign_bursts(shots, 1.5)
    twice = S.assign_bursts(once, 1.5)
    thrice = S.assign_bursts(twice, 1.5)
    assert [s.notes for s in once] == [s.notes for s in twice] == [s.notes for s in thrice]
    over = [s.notes for s in thrice if s.burst_index > MAX_BALLS_HELD]
    assert len(over) == 3 and all(n.count("burst exceeds") == 1 for n in over)


def test_assign_bursts_keeps_other_notes_and_drops_stale_tag():
    base = blank_shot(1, 0.0)
    base = Shot(**{**base.__dict__, "notes": "track extrapolated"})
    tagged = Shot(**{**base.__dict__, "notes": "track extrapolated; burst exceeds 4 balls (index 9)"})
    out = S.assign_bursts([tagged], 1.5)[0]
    assert out.notes == "track extrapolated"   # index 1: the stale tag is removed
    assert S.assign_bursts([base], 1.5)[0].notes == "track extrapolated"


# ------------------------------------------------- MISS needs evidence; mid-air is UNKNOWN
G = 386.09


def _geometry(state=None):
    from hiveshot.field import HiveState
    st = state or HiveState("red", "audience")
    return S.opening_classifier("red", "audience", st), st


def _flight(dx, speed_y, vz, t_end=None, z0=12.0, dt=1 / 60, stop_below=None, x0=None):
    """Ballistic track toward the red audience up-CELL opening (centre y = +24.25 in,
    balls arrive from +Y). dx shifts the line sideways of the opening centre."""
    from hiveshot.field import HiveState, cell_opening_plane
    c, _ = cell_opening_plane("red", "audience", HiveState())
    pts, i = [], 0
    while True:
        t = i * dt
        z = z0 + vz * t - 0.5 * G * t * t
        pts.append(Point3D(t, c[0] + dx, c[1] + 100.0 - speed_y * t, z))
        i += 1
        if t_end is not None and t >= t_end:
            break
        if stop_below is not None and z < stop_below and t > vz / G:
            break
        if t > 3:
            break
    return Track3D(1, pts, BallType.POLLEN)


# a shot that arrives at the opening centre after 0.7 s, descending
_T = 0.7
_SPEED_Y = 100.0 / _T
_VZ = (59.55 - 12.0 + 0.5 * G * _T * _T) / _T
_APEX_T = _VZ / G


def _classify(track, cfg_tuple):
    cfg, crosses, inside = cfg_tuple
    return S.classify(track, crosses, inside, cfg)


def test_complete_made_trajectory_is_made_control():
    geo, _ = _geometry()
    tr = _flight(0.0, _SPEED_Y, _VZ, t_end=_T + 0.05)
    assert _classify(tr, geo).result == ShotResult.MADE


def test_truncated_made_trajectory_at_apex_is_unknown():
    geo, _ = _geometry()
    tr = _flight(0.0, _SPEED_Y, _VZ, t_end=_APEX_T)       # cut at the apex, still rising
    assert tr.points[-1].z > 47.5
    c = _classify(tr, geo)
    assert c.result == ShotResult.UNKNOWN and c.entry_t is None
    shot = S.build_shot(tr, "s", 1, geo[1:], BallType.POLLEN, geo[0])
    assert shot.result == ShotResult.UNKNOWN and "track lost" in shot.notes
    early = _flight(0.0, _SPEED_Y, _VZ, t_end=0.40)       # cut well before the opening
    c = _classify(early, geo)
    assert c.result == ShotResult.UNKNOWN and c.note == S.NOTE_LOST_MIDAIR
    shot = S.build_shot(early, "s", 1, geo[1:], BallType.POLLEN, geo[0])
    assert S.NOTE_LOST_MIDAIR in shot.notes


@pytest.mark.parametrize("cut_t", [0.58, 0.64, 0.68])
def test_track_lost_near_the_opening_is_unknown_with_note(cut_t):
    geo, _ = _geometry()
    tr = _flight(0.0, _SPEED_Y, _VZ, t_end=cut_t)         # within 24 in, above the lower edge
    c = _classify(tr, geo)
    assert c.result == ShotResult.UNKNOWN
    assert c.note == "track lost near the opening"
    shot = S.build_shot(tr, "s", 1, geo[1:], BallType.POLLEN, geo[0])
    assert "track lost near the opening" in shot.notes


def test_full_miss_landing_on_the_floor_is_miss():
    geo, _ = _geometry()
    tr = _flight(0.0, 0.55 * _SPEED_Y, _VZ, stop_below=2.0)   # falls short, lands
    assert tr.points[-1].z < 6.0
    c = _classify(tr, geo)
    assert c.result == ShotResult.MISS and c.note == ""
    # without the plane evidence the floor alone still decides
    geo[0].plane_miss = None
    assert _classify(tr, geo).result == ShotResult.MISS


def test_pass_beside_the_opening_and_continue_below_it_is_miss():
    geo, _ = _geometry()
    wide = _flight(60.0, _SPEED_Y, _VZ, stop_below=40.0)  # 60 in to the side, drops below it
    assert wide.points[-1].z < geo[0].opening_bottom_z
    assert _classify(wide, geo).result == ShotResult.MISS
    geo[0].plane_miss = None                              # z below the lower edge alone
    assert _classify(wide, geo).result == ShotResult.MISS


def test_clear_plane_crossing_outside_the_opening_is_miss_even_while_still_high():
    geo, _ = _geometry()
    tr = _flight(60.0, _SPEED_Y, _VZ, t_end=_T + 0.08)    # ends just past the plane, z ~ 59
    assert tr.points[-1].z > 47.5
    assert _classify(tr, geo).result == ShotResult.MISS
    before_plane = _flight(60.0, _SPEED_Y, _VZ, t_end=0.55)
    assert _classify(before_plane, geo).result == ShotResult.UNKNOWN   # not there yet


def test_shot_just_outside_the_opening_edge_is_not_clearly_a_miss():
    geo, _ = _geometry()
    # 11.5 in off centre: 1.5 in outside the 10 in half width, inside radius + margin
    tr = _flight(11.5, _SPEED_Y, _VZ, t_end=_T + 0.05)
    assert _classify(tr, geo).result == ShotResult.UNKNOWN


def test_without_geometry_a_midair_stop_is_unknown_and_landing_is_miss():
    tr = make_track()                                      # still rising at the end
    res, t = S.classify_track(tr, lambda a, b, r: None, lambda p: False)
    assert res == ShotResult.UNKNOWN and t is None
    landing = _flight(0.0, 0.5 * _SPEED_Y, _VZ, stop_below=2.0)
    assert S.classify_track(landing, lambda a, b, r: None, lambda p: False)[0] == ShotResult.MISS


def test_classify_track_tuple_api_unchanged_for_crossings():
    tr = make_track()
    assert S.classify_track(tr, stub_cross(tr, 10), inside_from(tr, 11))[0] == ShotResult.MADE


def test_dropped_note_roundtrip_and_summary_fields():
    s = blank_shot(1, 2.0)
    assert S.dropped_during_flight(s.notes) == 0
    s = Shot(**{**s.__dict__, "notes": f"x; {S.dropped_note(7)}"})
    assert S.dropped_during_flight(s.notes) == 7
    d = S.summarize(s, session_start=1_700_000_000.0)
    assert d["dropped_during_flight"] == 7 and d["t_launch_wall"] is not None
    assert S.summarize(blank_shot(2, 1.0))["t_launch_wall"] is None


# ------------------------------------------------ bounce-out only through the opening
def _made_flight():
    return _flight(0.0, _SPEED_Y, _VZ, t_end=_T + 0.05)


def test_bounce_out_through_the_opening_is_bounce_out():
    geo, _ = _geometry()
    pts = list(_made_flight().points)
    dt = 1 / 60
    back = [Point3D(pts[-1].t + (k + 1) * dt, p.x, p.y, p.z)
            for k, p in enumerate(reversed(pts[-8:-1]))]       # retraces its path outward
    tr = Track3D(1, pts + back, BallType.POLLEN)
    c = _classify(tr, geo)
    assert c.result == ShotResult.BOUNCE_OUT and c.entry_t is not None


def test_leaving_the_cell_through_a_wall_is_unknown_with_note():
    geo, _ = _geometry()
    pts = list(_made_flight().points)
    dt = 1 / 60
    last = pts[-1]
    side = [Point3D(last.t + k * dt, last.x + 6.0 * k, last.y, last.z) for k in range(1, 7)]
    tr = Track3D(1, pts + side, BallType.POLLEN)
    c = _classify(tr, geo)
    assert c.result == ShotResult.UNKNOWN and c.note == S.NOTE_LEFT_WALL
    assert c.entry_t is not None
    shot = S.build_shot(tr, "s", 1, geo[1:], BallType.POLLEN, geo[0])
    assert shot.result == ShotResult.UNKNOWN and "through a wall" in shot.notes


def test_staying_inside_for_the_settle_time_is_made_even_if_it_later_leaves_sideways():
    geo, _ = _geometry()
    cfg, crosses, inside = geo
    cfg.settle_time_s = 0.05                                # settled almost at once
    pts = list(_made_flight().points)
    last = pts[-1]
    side = [Point3D(last.t + k / 60, last.x + 6.0 * k, last.y, last.z) for k in range(1, 7)]
    tr = Track3D(1, pts + side, BallType.POLLEN)
    assert S.classify(tr, crosses, inside, cfg).result == ShotResult.MADE


def test_track_starting_mid_flight_is_classified_normally():
    geo, _ = _geometry()
    full = _made_flight()
    mid = Track3D(1, [p for p in full.points if p.t >= 0.3], BallType.POLLEN)   # first frame mid-air
    assert _classify(mid, geo).result == ShotResult.MADE
    shot = S.build_shot(mid, "s", 1, geo[1:], BallType.POLLEN, geo[0])
    assert shot.result == ShotResult.MADE and shot.exit_speed_ips and shot.exit_speed_ips > 0
    miss = _flight(0.0, 0.55 * _SPEED_Y, _VZ, stop_below=2.0)
    miss = Track3D(1, [p for p in miss.points if p.t >= 0.3], BallType.POLLEN)
    assert _classify(miss, geo).result == ShotResult.MISS

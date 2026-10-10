import threading

from hiveshot.models import (
    BallType,
    DragFit,
    ParabolaFit,
    Point3D,
    Shot,
    ShotResult,
    TipEvent,
    Track3D,
)
from hiveshot.store import Store, shot_full, shot_summary


def make_shot(sid, t=1.0, result=ShotResult.MADE):
    tr = Track3D(track_id=3, ball_type=BallType.POLLEN,
                 points=[Point3D(t + i * 0.1, i, 2 * i, 10 + i, 0.1) for i in range(5)])
    return Shot(
        shot_id=0, session_id=sid, t_launch=t, burst_id=1, burst_index=1,
        ball_type=BallType.POLLEN, result=result, exit_speed_ips=300.0,
        launch_angle_deg=55.0, launch_azimuth_deg=90.0, launch_point=(0.0, 1.0, 12.0),
        apex_z_in=70.0, parabola=ParabolaFit(-0.01, 1.2, 12.0, 0.3, 55.0, 300.0),
        drag=DragFit((1.0, 2.0, 3.0), (0.0, 1.0, 12.0), 0.001, 0.2), track=tr)


def test_crud(tmp_path):
    s = Store(tmp_path / "t.db")
    sid = s.create_session("one")
    assert s.session_exists(sid)
    a = s.add_shot(make_shot(sid, 1.0))
    b = s.add_shot(make_shot(sid, 2.0, ShotResult.MISS))
    assert a.shot_id != b.shot_id
    got = s.get_shot(a.shot_id)
    assert got.track.points[2].z == 12 and got.parabola.b == 1.2
    assert got.drag.k_per_in == 0.001 and got.launch_point == (0.0, 1.0, 12.0)
    assert [x.shot_id for x in s.list_shots(sid)] == [a.shot_id, b.shot_id]
    s.update_burst(b.shot_id, 1, 2, "n")
    assert s.get_shot(b.shot_id).burst_index == 2
    s.add_tip(TipEvent(3.0, sid, "red", "far", a.shot_id))
    assert s.list_tips(sid)[0].new_up_cell == "far"
    summ = s.session_summary(sid)
    assert summ["shots"] == 2 and summ["made"] == 1 and summ["ended_at"] is None
    assert s.end_session(sid)
    assert s.session_summary(sid)["ended_at"] is not None
    assert s.get_shot(9999) is None
    assert shot_summary(got)["exit_speed_mps"] == 300.0 * 0.0254
    assert len(shot_full(got)["track"]) == 5
    s.close()


def test_restart_persistence(tmp_path):
    p = tmp_path / "t.db"
    s = Store(p)
    sid = s.create_session("persist")
    sh = s.add_shot(make_shot(sid))
    s.close()
    s2 = Store(p)
    assert s2.session_exists(sid)
    got = s2.get_shot(sh.shot_id)
    assert got is not None and got.result == ShotResult.MADE
    assert len(s2.list_shots(sid)) == 1
    s2.close()


def test_concurrent_adds(tmp_path):
    s = Store(tmp_path / "t.db")
    sid = s.create_session("c")
    out = []

    def work(i):
        out.append(s.add_shot(make_shot(sid, float(i))).shot_id)

    ths = [threading.Thread(target=work, args=(i,)) for i in range(4)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    assert len(set(out)) == 4
    assert len(s.list_shots(sid)) == 4
    s.close()


def test_tip_ids_cause_update_and_ensure_session(tmp_path):
    s = Store(tmp_path / "t.db")
    sid = s.create_session("x")
    shot = s.add_shot(make_shot(sid))
    t1 = s.add_tip(TipEvent(1.0, sid, "red", "far", None))
    t2 = s.add_tip(TipEvent(2.0, sid, "red", "audience", None))
    assert t1 != t2
    s.set_tip_cause(t2, shot.shot_id)
    assert [t.caused_by_shot_id for t in s.list_tips(sid)] == [None, shot.shot_id]
    s.ensure_session("unassigned", "Unassigned shots")
    s.ensure_session("unassigned", "again")      # idempotent
    assert s.session_exists("unassigned")
    assert "unassigned" not in s.open_sessions()
    assert len([x for x in s.list_sessions() if x["session_id"] == "unassigned"]) == 1
    s.close()
    s.close()                                     # idempotent

"""Demo mode: --demo flag, /api/demo/start and /stop, separate data dir, user config untouched."""

import hashlib
import json
import time

import pytest

from hiveshot import app as appmod
from hiveshot import config as cfgmod
from hiveshot.app import build_parser, create_app
from tests.test_app import _serve, _shutdown


def _wait(pred, timeout=30.0, step=0.1):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(step)
    return pred()


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_demo_flag_parsing():
    a = build_parser().parse_args(["--demo"])
    assert a.demo is True and a.autostart is False
    a = build_parser().parse_args(["--demo", "--port", "8781", "--data-dir", "x"])
    assert a.demo and a.port == 8781 and a.data_dir == "x"
    assert build_parser().parse_args([]).demo is False


def test_demo_config_shape():
    cfg = appmod.demo_config()
    assert cfg.alliance == "red" and cfg.hive_up_cell == "audience"
    assert [s.cam_id for s in cfg.sources] == ["cam0", "cam1"]
    assert all(s.kind == "file" and s.loop and s.realtime for s in cfg.sources)
    fixtures = {s.target.split("/")[1] for s in cfg.sources}
    assert len(fixtures) == 1 and fixtures <= {"synth_20", "synth_basic"}
    assert cfg.session_name_template == "Demo {date} {time}"
    assert not any(s.kind == "rtmp" for s in cfg.sources)


@pytest.fixture()
def fast_demo(monkeypatch):
    monkeypatch.setattr(appmod, "DEMO_REALTIME", False)       # flat out, not at video speed


def test_demo_start_stop_round_trip_leaves_user_config_alone(tmp_path, fast_demo):
    cfg_path = tmp_path / "config.json"
    user = cfgmod.AppConfig(burst_gap_s=2.5, sources=[
        cfgmod.SourceConfig(cam_id="a", kind="device", target=0),
        cfgmod.SourceConfig(cam_id="b", kind="device", target=1)])
    cfgmod.save(cfg_path, user)
    before = _sha(cfg_path)
    server, th, c = _serve(create_app(cfg_path, tmp_path / "data"))
    try:
        user_sid = c.j("POST", "/api/sessions", {"name": "mine"})[1]["session_id"]
        assert c.j("GET", "/api/pipeline/status")[1]["demo"] is False
        s, j = c.j("POST", "/api/demo/start")
        assert s == 200 and j["ok"] is True and j["session_id"]
        st = c.j("GET", "/api/pipeline/status")[1]
        assert st["demo"] is True and st["running"] is True and st["session_id"] == j["session_id"]
        assert st["rtmp"]["running"] is False
        sessions = c.j("GET", "/api/sessions")[1]
        assert [x["session_id"] for x in sessions] == [j["session_id"]]       # demo db only
        assert sessions[0]["name"].startswith("Demo 20")
        assert [x["cam_id"] for x in c.j("GET", "/api/config")[1]["sources"]] == ["cam0", "cam1"]
        # a config edit during the demo applies in memory but is never written to disk
        assert c.j("PUT", "/api/config", {"burst_gap_s": 9.0})[0] == 200
        assert c.j("POST", "/api/hive/state", {"alliance": "red", "up_cell": "far"})[0] == 200
        assert _sha(cfg_path) == before
        # a shot appears within 30 s and the session keeps growing while the footage loops
        assert _wait(lambda: c.j("GET", "/api/sessions")[1][0]["shots"] >= 1, 30)
        n1 = c.j("GET", "/api/sessions")[1][0]["shots"]
        assert _wait(lambda: c.j("GET", "/api/sessions")[1][0]["shots"] > n1, 60)
        assert (tmp_path / "data" / "demo" / "hiveshot.db").exists()

        s, j2 = c.j("POST", "/api/demo/stop")
        assert s == 200 and j2 == {"ok": True}
        st = c.j("GET", "/api/pipeline/status")[1]
        assert st["demo"] is False and st["running"] is False
        assert _sha(cfg_path) == before                                      # untouched
        assert c.j("GET", "/api/config")[1]["burst_gap_s"] == 2.5            # user config back
        assert [x["cam_id"] for x in c.j("GET", "/api/config")[1]["sources"]] == ["a", "b"]
        assert [x["session_id"] for x in c.j("GET", "/api/sessions")[1]] == [user_sid]
        # and it can be run again
        assert c.j("POST", "/api/demo/start")[0] == 200
        assert c.j("GET", "/api/pipeline/status")[1]["demo"] is True
    finally:
        _shutdown(server, th)
    assert _sha(cfg_path) == before
    assert json.loads(cfg_path.read_text())["burst_gap_s"] == 2.5


def test_demo_burst_assignment_survives_the_loop(tmp_path, fast_demo):
    """After the footage wraps, t_source keeps rising, so later shots are not folded back
    into the first burst."""
    server, th, c = _serve(create_app(None, tmp_path / "data"))
    try:
        sid = c.j("POST", "/api/demo/start")[1]["session_id"]
        assert _wait(lambda: len(c.j("GET", f"/api/sessions/{sid}/shots")[1]) >= 8, 90)
        shots = c.j("GET", f"/api/sessions/{sid}/shots")[1]
        launches = [x["t_launch"] for x in shots]
        assert launches == sorted(launches)
        assert len({x["burst_id"] for x in shots}) >= 2
        assert all(1 <= x["burst_index"] for x in shots)
    finally:
        _shutdown(server, th)


def test_demo_cli_mode_runs_in_a_demo_subfolder(tmp_path, fast_demo):
    data = tmp_path / "data"
    user_cfg = data / "config.json"
    data.mkdir()
    cfgmod.save(user_cfg, cfgmod.AppConfig(burst_gap_s=3.0))
    before = _sha(user_cfg)
    server, th, c = _serve(create_app(None, data, demo=True))
    try:
        assert _wait(lambda: c.j("GET", "/api/pipeline/status")[1]["running"], 20)
        st = c.j("GET", "/api/pipeline/status")[1]
        assert st["demo"] is True and st["session_id"]
        assert _wait(lambda: c.j("GET", "/api/sessions")[1][0]["shots"] >= 1, 30)
        c.j("PUT", "/api/config", {"burst_gap_s": 7.0})
    finally:
        _shutdown(server, th)
    assert (data / "demo" / "hiveshot.db").exists()
    assert not (data / "hiveshot.db").exists()                 # the user's database untouched
    assert _sha(user_cfg) == before
    assert not (data / "demo" / "config.json").exists()

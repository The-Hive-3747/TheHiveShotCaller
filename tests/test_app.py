"""API tests. fastapi.testclient needs httpx2 (not installed and not installable here), so
the app is served by uvicorn in a background thread on an ephemeral port and driven with
urllib and websockets' sync client."""

import csv
import io
import json
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

import numpy as np
import pytest
import uvicorn
from websockets.sync.client import connect

from hiveshot import calib_targets, ingest
from hiveshot import config as cfgmod
from hiveshot.app import create_app


class Client:
    def __init__(self, port):
        self.base = f"http://127.0.0.1:{port}"
        self.port = port

    def req(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        r = urllib.request.Request(self.base + path, data=data, method=method,
                                   headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(r, timeout=20) as resp:
                return resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def get(self, path):
        return self.req("GET", path)

    def j(self, method, path, body=None):
        s, _, b = self.req(method, path, body)
        return s, (json.loads(b) if b else None)


def _serve(app):
    """Run app under uvicorn on an ephemeral port; returns (server, thread, Client)."""
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    deadline = time.time() + 10
    while time.time() < deadline and not (server.started and server.servers):
        time.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    return server, th, Client(port)


def _shutdown(server, th):
    server.should_exit = True
    th.join(timeout=30)
    assert not th.is_alive(), "server did not shut down"


@pytest.fixture()
def client(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfgmod.save(cfg_path, cfgmod.AppConfig())
    app = create_app(cfg_path, tmp_path / "data")
    server, th, c = _serve(app)
    yield c
    _shutdown(server, th)


def test_config_get_put(client):
    _, c = client.j("GET", "/api/config")
    assert [s["cam_id"] for s in c["sources"]] == ["cam0", "cam1"]
    assert c["alliance"] == "red" and c["hive_up_cell"] == "audience"
    s, j = client.j("PUT", "/api/config", {"burst_gap_s": 2.0, "robot": {"length": 20}})
    assert s == 200
    assert j["burst_gap_s"] == 2.0 and j["robot"]["length"] == 20
    assert j["robot"]["width"] == 18 and len(j["sources"]) == 2
    assert client.j("GET", "/api/config")[1]["burst_gap_s"] == 2.0
    assert client.req("PUT", "/api/config", {"alliance": "green"})[0] == 422


def test_sessions_and_stats(client):
    sid = client.j("POST", "/api/sessions", {"name": "t1"})[1]["session_id"]
    lst = client.j("GET", "/api/sessions")[1]
    assert lst[0]["session_id"] == sid and lst[0]["name"] == "t1"
    assert lst[0]["shots"] == 0 and lst[0]["ended_at"] is None
    st = client.j("GET", f"/api/sessions/{sid}/stats")[1]
    assert st["shots"] == 0 and st["made"] == 0 and st["make_rate"] == 0.0
    assert set(st["failure_order_hist"]) == {"1", "2", "3", "4", "5"}
    assert client.j("GET", f"/api/sessions/{sid}/shots")[1] == []
    assert client.j("GET", f"/api/sessions/{sid}/tips")[1] == []
    assert client.j("POST", f"/api/sessions/{sid}/end")[1] == {"ok": True}
    assert client.j("GET", "/api/sessions")[1][0]["ended_at"] is not None
    sid2 = client.j("POST", "/api/sessions", {"name": "t2"})[1]["session_id"]
    assert sid2 != sid
    assert client.req("GET", "/api/sessions/nope/stats")[0] == 404
    assert client.req("GET", "/api/shots/12345")[0] == 404


def test_csv_export(client):
    sid = client.j("POST", "/api/sessions", {"name": "t"})[1]["session_id"]
    s, h, b = client.get(f"/api/sessions/{sid}/export.csv")
    assert s == 200 and h["content-type"].startswith("text/csv")
    assert b.decode().splitlines()[0].startswith("shot_id,session_id")


def test_geometry_devices_calib(client, monkeypatch):
    # never probe real capture hardware from a test
    monkeypatch.setattr(ingest, "list_devices", lambda max_index=10, **kw: [
        {"index": 0, "width": 640, "height": 480, "fps": 30.0, "backend": "fake"}])
    g = client.j("GET", "/api/field/geometry")[1]
    assert len(g["wireframe"]) > 10 and "hives" in g
    s, d = client.j("GET", "/api/devices?max_index=1")
    assert s == 200 and d == [{"index": 0, "width": 640, "height": 480, "fps": 30.0}]
    cal = client.j("GET", "/api/calib")[1]
    assert len(cal["intrinsics"]) == 2 and len(cal["extrinsics"]) == 2  # embedded fixture calib


def test_checkerboard_pdf_and_reference_points(client, tmp_path):
    s, h, b = client.get("/api/calib/checkerboard.pdf")
    assert s == 200 and h["content-type"] == "application/pdf"
    assert b.startswith(b"%PDF")
    assert "checkerboard_10x7_1in.pdf" in h["content-disposition"]
    cached = tmp_path / "data" / "checkerboard_10x7_1in.pdf"
    assert cached.read_bytes() == b
    mtime = cached.stat().st_mtime_ns
    assert client.get("/api/calib/checkerboard.pdf")[2] == b
    assert cached.stat().st_mtime_ns == mtime            # generated once, then served from cache

    s, pts = client.j("GET", "/api/calib/points")
    assert s == 200 and len(pts) == 8
    expected = calib_targets.field_reference_points()
    for got, (name, xyz) in zip(pts, expected, strict=True):
        assert got["name"] == name and got["xyz"] == pytest.approx(list(xyz))
        assert len(got["xyz"]) == 3
    assert [p["name"] for p in pts] == calib_targets.reference_point_names()


def test_hive_state_roundtrip(client):
    s, _ = client.j("POST", "/api/hive/state", {"alliance": "blue", "up_cell": "far"})
    assert s == 200
    hs = client.j("GET", "/api/pipeline/status")[1]["hive_state"]
    assert hs == {"alliance": "blue", "up_cell": "far"}
    assert client.req("POST", "/api/hive/state", {"alliance": "x", "up_cell": "far"})[0] == 422


def test_preview_before_start_is_404(client):
    assert client.get("/api/preview/cam0.jpg")[0] == 404
    assert client.get("/api/preview/cam0.mjpg")[0] == 404
    assert client.get("/api/preview/nope.jpg")[0] == 404
    st = client.j("GET", "/api/pipeline/status")[1]
    assert st["running"] is False and set(st["cameras"]) == {"cam0", "cam1"}
    assert set(st["rtmp"]) == {"available", "running", "urls"}


def test_static_root_does_not_crash(client):
    assert client.get("/")[0] in (200, 404)


def test_websocket_status(client):
    with connect(f"ws://127.0.0.1:{client.port}/ws", open_timeout=3) as ws:
        msg = json.loads(ws.recv(timeout=3))
    assert msg["type"] == "status" and "cameras" in msg and "hive_state" in msg


def test_restart_keeps_session_and_shots(tmp_path):
    """Run synth_basic to completion, shut the server down, start a NEW app instance on the
    same data dir: the session, its shots, tracks and CSV export must be served from disk."""
    cfg_path = tmp_path / "config.json"
    data = tmp_path / "data"
    cfg = cfgmod.AppConfig(sources=[
        cfgmod.SourceConfig(cam_id=f"cam{i}", kind="file",
                            target=f"fixtures/synth_basic/cam{i}.mp4", realtime=False)
        for i in (0, 1)])
    cfgmod.save(cfg_path, cfg)

    server, th, c = _serve(create_app(cfg_path, data, autostart=True))
    try:
        deadline = time.time() + 60
        st = {}
        while time.time() < deadline:
            st = c.j("GET", "/api/pipeline/status")[1]
            if st["last_shot_id"] == 6:
                break
            time.sleep(0.25)
        assert st["last_shot_id"] == 6, f"6th shot not stored within 60 s: {st}"
        cams = st["cameras"]
        assert all(v["ended"] and not v["is_alive"] for v in cams.values()), cams
    finally:
        _shutdown(server, th)

    from hiveshot.store import Store
    chk = Store(data / "hiveshot.db")
    left_open = chk.open_sessions()
    chk.close()
    assert len(left_open) == 1, "precondition: the first run leaves its session open"

    server2, th2, c2 = _serve(create_app(cfg_path, data))
    try:
        sessions = c2.j("GET", "/api/sessions")[1]
        assert len(sessions) == 1 and sessions[0]["shots"] == 6
        assert sessions[0]["ended_at"] is not None, "stale open session not ended at startup"
        sid = sessions[0]["session_id"]
        listed = c2.j("GET", f"/api/sessions/{sid}/shots")[1]
        t_launch = [x["t_launch"] for x in listed]
        assert len(listed) == 6 and t_launch == sorted(t_launch)
        started = sessions[0]["started_at"]
        for x in listed:
            assert x["dropped_during_flight"] == 0
            assert datetime.fromisoformat(x["t_launch_wall"]).timestamp() == pytest.approx(
                started + x["t_launch"], abs=0.002)
        shot = c2.j("GET", "/api/shots/1")[1]
        assert len(shot["track"]) >= 4
        assert shot["parabola"] is not None
        s, _, body = c2.get(f"/api/sessions/{sid}/export.csv")
        assert s == 200 and len(body.decode().splitlines()) == 7
        rows = list(csv.DictReader(io.StringIO(body.decode())))
        assert datetime.fromisoformat(rows[0]["t_launch_wall"]).timestamp() == pytest.approx(
            started + float(rows[0]["t_launch"]), abs=0.002)
        assert c2.j("GET", "/api/pipeline/status")[1]["running"] is False
    finally:
        _shutdown(server2, th2)


SHOT_SUMMARY_KEYS = {"shot_id", "t_launch", "burst_id", "burst_index", "ball_type", "result",
                     "exit_speed_ips", "exit_speed_mps", "launch_angle_deg",
                     "launch_azimuth_deg", "apex_z_in", "equation", "clip_url",
                     "dropped_during_flight", "t_launch_wall"}


def _lockstep_cfg(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfgmod.save(cfg_path, cfgmod.AppConfig(sources=[
        cfgmod.SourceConfig(cam_id=f"cam{i}", kind="file",
                            target=f"fixtures/synth_basic/cam{i}.mp4", realtime=False)
        for i in (0, 1)]))
    return cfg_path


def test_websocket_receives_shot_events(tmp_path):
    app = create_app(_lockstep_cfg(tmp_path), tmp_path / "data")
    server, th, c = _serve(app)
    try:
        with connect(f"ws://127.0.0.1:{c.port}/ws", open_timeout=3) as ws:
            assert json.loads(ws.recv(timeout=3))["type"] == "status"
            assert c.j("POST", "/api/pipeline/start")[1] == {"ok": True, "running": True}
            shot = None
            deadline = time.time() + 30
            while time.time() < deadline and shot is None:
                msg = json.loads(ws.recv(timeout=max(0.1, deadline - time.time())))
                if msg["type"] == "shot":
                    shot = msg["shot"]
        assert shot is not None, "no shot message within 30 s"
        assert set(shot) == SHOT_SUMMARY_KEYS
        assert shot["result"] in ("made", "miss", "bounce_out", "unknown")
        assert shot["exit_speed_ips"] > 0
    finally:
        _shutdown(server, th)


def test_put_config_rejects_source_change_while_running(tmp_path):
    app = create_app(_lockstep_cfg(tmp_path), tmp_path / "data", autostart=True)
    server, th, c = _serve(app)
    try:
        assert c.j("GET", "/api/pipeline/status")[1]["running"] is True
        before = c.j("GET", "/api/config")[1]
        s, j = c.j("PUT", "/api/config", {"sources": list(reversed(before["sources"]))})
        assert s == 409 and "sources" in j["detail"]
        assert c.j("GET", "/api/config")[1]["sources"] == before["sources"]   # not applied
        s, j = c.j("PUT", "/api/config", {"burst_gap_s": 2.25, "stitch_gap_s": 1.0})
        assert s == 200 and j["burst_gap_s"] == 2.25
        pl = app.state.hs.pipeline
        assert pl._rcfg.burst_gap_s == 2.25 and pl._rcfg.stitch_gap_s == 1.0
        assert [x.cam_id for x in pl._rcfg.sources] == ["cam0", "cam1"]
        # repeated start while running is a no-op
        assert c.j("POST", "/api/pipeline/start")[1]["running"] is True
    finally:
        _shutdown(server, th)


def test_session_end_is_visible_in_status_and_shots_go_unassigned(tmp_path):
    app = create_app(_lockstep_cfg(tmp_path), tmp_path / "data")
    server, th, c = _serve(app)
    try:
        sid = c.j("POST", "/api/sessions", {"name": "s"})[1]["session_id"]
        c.j("POST", "/api/pipeline/start")
        assert c.j("GET", "/api/pipeline/status")[1]["session_id"] == sid
        assert c.j("POST", f"/api/sessions/{sid}/end")[1] == {"ok": True}
        assert c.j("GET", "/api/pipeline/status")[1]["session_id"] is None
        deadline = time.time() + 60
        while time.time() < deadline:
            if c.j("GET", "/api/pipeline/status")[1]["last_shot_id"] == 6:
                break
            time.sleep(0.25)
        sessions = {x["session_id"]: x for x in c.j("GET", "/api/sessions")[1]}
        assert sessions[sid]["shots"] == 0
        assert sessions["unassigned"]["shots"] == 6
    finally:
        _shutdown(server, th)


def test_intrinsics_save_marks_extrinsics_stale(tmp_path):
    app = create_app(_lockstep_cfg(tmp_path), tmp_path / "data")
    server, th, c = _serve(app)
    try:
        st = app.state.hs
        intr, ext = st.pipeline.calibration()
        assert set(ext) == {"cam0", "cam1"}
        assert all(not e["stale"] for e in c.j("GET", "/api/calib")[1]["extrinsics"])
        # what intr_stop does after a new intrinsics solve for cam0
        st.save_calib(intr, ext, {"cam0"} | st.pipeline.stale_extrinsics())
        cal = {e["cam_id"]: e for e in c.j("GET", "/api/calib")[1]["extrinsics"]}
        assert cal["cam0"]["stale"] is True and cal["cam1"]["stale"] is False
        raw = json.loads((tmp_path / "data" / "calibration.json").read_text())
        assert [e.get("stale", False) for e in raw["extrinsics"]] == [True, False]
        # solving new extrinsics for cam0 clears the flag on the next save
        st.save_calib(intr, ext, st.pipeline.stale_extrinsics() - {"cam0"})
        assert not any(e["stale"] for e in c.j("GET", "/api/calib")[1]["extrinsics"])
    finally:
        _shutdown(server, th)


# ------------------------------------------------------- config validation (PUT /api/config)
def _src(cam, kind="file", target="x.mp4"):
    return {"cam_id": cam, "kind": kind, "target": target}


@pytest.mark.parametrize("sources, needle", [
    ([_src("cam0"), _src("cam1", kind="banana")], "kind"),
    ([_src("cam0"), _src("cam0")], "unique"),
    ([_src("cam0"), _src("cam1", target="")], "target"),
    ([_src("cam0"), _src("cam1", target="   ")], "target"),
    ([_src("cam0"), _src("")], "cam_id"),
])
def test_put_config_rejects_bad_sources(client, sources, needle):
    before = client.j("GET", "/api/config")[1]
    s, j = client.j("PUT", "/api/config", {"sources": sources})
    assert s == 422 and needle in json.dumps(j)
    assert client.j("GET", "/api/config")[1] == before            # nothing applied or saved


def test_put_config_accepts_every_valid_kind(client):
    srcs = [_src("cam0", "file"), _src("cam1", "device", 0), _src("cam2", "rtmp", "cam2"),
            _src("cam3", "url", "http://127.0.0.1:1/x.mjpg")]
    s, j = client.j("PUT", "/api/config", {"sources": srcs})
    assert s == 200 and [x["kind"] for x in j["sources"]] == ["file", "device", "rtmp", "url"]
    assert client.j("PUT", "/api/config", {"sources": [_src("cam0", "device", 0)]})[0] == 200


# ------------------------------------------------------------- calibration cross-check
def _click_both_cameras(c, noise=None, swap=None, expect=200):
    """Solve both cameras' extrinsics from reference points projected with the (embedded
    fixture) truth calibration; returns the projected clicks."""
    from hiveshot import calib
    from hiveshot.models import CameraExtrinsics, CameraIntrinsics
    cal = c.j("GET", "/api/calib")[1]
    intr = {i["cam_id"]: CameraIntrinsics(**{**i, "dist": tuple(i["dist"])})
            for i in cal["intrinsics"]}
    ext = {e["cam_id"]: CameraExtrinsics(**{
        k: (tuple(v) if k in ("rvec", "tvec") else v)
        for k, v in e.items() if k != "stale"}) for e in cal["extrinsics"]}
    ref = calib_targets.field_reference_points()
    out = {}
    for cam in ("cam0", "cam1"):
        uv = calib.project(intr[cam], ext[cam], np.array([p for _, p in ref]))
        if noise is not None:
            uv = uv + noise(cam)
        pts = [{"name": n, "u": float(u), "v": float(v)} for (n, _), (u, v) in zip(ref, uv, strict=True)]
        if swap and cam == "cam1":                     # two clicks on each other's point
            pts[0]["u"], pts[0]["v"], pts[1]["u"], pts[1]["v"] = (
                pts[1]["u"], pts[1]["v"], pts[0]["u"], pts[0]["v"])
        s, j = c.j("POST", f"/api/calib/extrinsics/{cam}", {"points": pts})
        assert s == expect, j
        out[cam] = pts
    return out


def test_crosscheck_needs_clicks(client):
    s, j = client.j("POST", "/api/calib/crosscheck")
    assert s == 409 and "extrinsics" in j["detail"]


def test_crosscheck_reports_small_error_for_clean_clicks_and_persists_them(client, tmp_path):
    clicks = _click_both_cameras(client)
    s, j = client.j("POST", "/api/calib/crosscheck")
    assert s == 200
    assert len(j["points"]) == 8
    ref = dict(calib_targets.field_reference_points())
    for p in j["points"]:
        assert set(p) >= {"name", "xyz_measured", "xyz_expected", "error_in"}
        assert p["xyz_expected"] == pytest.approx(list(ref[p["name"]]))
        assert p["error_in"] == pytest.approx(
            sum((m - e) ** 2 for m, e in zip(p["xyz_measured"], p["xyz_expected"], strict=True)) ** 0.5)
    assert j["max_error_in"] == pytest.approx(max(p["error_in"] for p in j["points"]))
    assert j["max_error_in"] < 0.5 and j["within_1_in"] is True
    # nothing was held out (no frames, no tags): the answer is labelled in-sample
    assert j["out_of_sample"] is False and "in-sample" in j["warning"]
    s, j2 = client.j("POST", "/api/calib/crosscheck", {"in_sample": True})
    assert s == 200 and j2["out_of_sample"] is False and "warning" not in j2
    saved = json.loads((tmp_path / "data" / "calibration.json").read_text())
    assert {c: [(p["name"], round(p["u"], 3)) for p in v] for c, v in saved["clicks"].items()} \
        == {c: [(p["name"], round(p["u"], 3)) for p in v] for c, v in clicks.items()}


def test_crosscheck_flags_a_mis_clicked_point(client):
    def off(cam):                       # one click 11 px off per camera: RMSE 3.9 px, still saved
        d = np.zeros((8, 2))
        d[0 if cam == "cam0" else 3] = (11.0, 0.0)
        return d
    _click_both_cameras(client, noise=off)
    s, j = client.j("POST", "/api/calib/crosscheck")
    assert s == 200
    assert j["max_error_in"] > 0.5            # a clean click set measures below 0.5 in


def test_swapped_clicks_are_refused_not_saved(client):
    before = client.j("GET", "/api/calib")[1]
    s, j = client.j("POST", "/api/calib/extrinsics/cam1", {"points": _swapped_points(client)})
    assert s == 409 and j["refused"] is True and j["reprojection_px"] > 4.0
    assert "not saved" in j["detail"] and "previous calibration is kept" in j["detail"]
    assert client.j("GET", "/api/calib")[1]["extrinsics"] == before["extrinsics"]


def _swapped_points(c):
    from hiveshot import calib
    from hiveshot.models import CameraExtrinsics, CameraIntrinsics
    cal = c.j("GET", "/api/calib")[1]
    intr = {i["cam_id"]: CameraIntrinsics(**{**i, "dist": tuple(i["dist"])}) for i in cal["intrinsics"]}
    ext = {e["cam_id"]: CameraExtrinsics(**{k: (tuple(v) if k in ("rvec", "tvec") else v)
                                            for k, v in e.items() if k != "stale"})
           for e in cal["extrinsics"]}
    ref = calib_targets.field_reference_points()
    uv = calib.project(intr["cam1"], ext["cam1"], np.array([p for _, p in ref]))
    pts = [{"name": n, "u": float(u), "v": float(v)} for (n, _), (u, v) in zip(ref, uv, strict=True)]
    pts[0]["u"], pts[0]["v"], pts[1]["u"], pts[1]["v"] = pts[1]["u"], pts[1]["v"], pts[0]["u"], pts[0]["v"]
    return pts


def test_clicks_survive_a_later_calibration_save(client, tmp_path):
    _click_both_cameras(client)
    cal = client.j("GET", "/api/calib")[1]
    assert "clicks" not in cal                              # clicks are stored, not served
    # re-solving one camera rewrites the file; the other camera's clicks stay
    pts = json.loads((tmp_path / "data" / "calibration.json").read_text())["clicks"]["cam0"]
    assert client.j("POST", "/api/calib/extrinsics/cam1", {"points": pts})[0] == 200
    saved = json.loads((tmp_path / "data" / "calibration.json").read_text())
    assert set(saved["clicks"]) == {"cam0", "cam1"}


# ------------------------------------------------ status: calibration_loaded and warnings
def test_status_reports_calibration_loaded_and_warnings(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfgmod.save(cfg_path, cfgmod.AppConfig(calibration_path=str(tmp_path / "none.json"), sources=[
        cfgmod.SourceConfig(cam_id="a", kind="rtmp", target="a"),
        cfgmod.SourceConfig(cam_id="b", kind="rtmp", target="b")]))
    server, th, c = _serve(create_app(cfg_path, tmp_path / "data"))
    try:
        st = c.j("GET", "/api/pipeline/status")[1]
        assert st["calibration_loaded"] is False
        assert "no calibration loaded: 3D reconstruction disabled" in st["warnings"]
    finally:
        _shutdown(server, th)


def test_status_with_embedded_fixture_calibration_has_no_calibration_warning(client):
    """The bundled fixture videos carry a calibration so they reconstruct, but it is not an
    operator calibration: not "loaded" (the wizard opens), source "fixture", no warning."""
    st = client.j("GET", "/api/pipeline/status")[1]
    assert st["calibration_loaded"] is False and st["calibration_source"] == "fixture"
    assert st["warnings"] == []
    assert {c["calibration_source"] for c in st["cameras"].values()} == {"fixture"}


def test_field_size_in_config_and_geometry(client):
    cfg = client.j("GET", "/api/config")[1]
    assert cfg["field_size_in"] == 144.0
    geo = client.j("GET", "/api/field/geometry")[1]
    assert geo["field_size"] == 144.0 and geo["bounds"]["max"][:2] == [72.0, 72.0]
    s, cfg = client.j("PUT", "/api/config", {"field_size_in": 141.5})
    assert s == 200 and cfg["field_size_in"] == 141.5
    geo = client.j("GET", "/api/field/geometry")[1]
    assert geo["field_size"] == 141.5
    assert geo["bounds"]["min"][:2] == [-70.75, -70.75] and geo["bounds"]["max"][:2] == [70.75, 70.75]
    assert client.j("PUT", "/api/config", {"field_size_in": 10})[0] == 422     # not a field
    assert client.j("GET", "/api/config")[1]["field_size_in"] == 141.5


# ----------------------------------------------------- calibration provenance and save gates
def _device_app(tmp_path, **kw):
    cfg_path = tmp_path / "config.json"
    cfgmod.save(cfg_path, cfgmod.AppConfig(sources=[
        cfgmod.SourceConfig(cam_id="a", kind="device", target=0),
        cfgmod.SourceConfig(cam_id="b", kind="device", target=1)], **kw))
    return create_app(cfg_path, tmp_path / "data")


def test_fresh_install_with_real_sources_is_not_calibrated(tmp_path):
    """Device sources with no calibration file: no fixture calibration is borrowed, nothing is
    "loaded", the sources only have default lens intrinsics."""
    server, th, c = _serve(_device_app(tmp_path))
    try:
        st = c.j("GET", "/api/pipeline/status")[1]
        assert st["calibration_loaded"] is False and st["calibration_source"] == "default_intrinsics"
        assert {v["calibration_source"] for v in st["cameras"].values()} == {"default_intrinsics"}
        assert {v["intrinsics_source"] for v in st["cameras"].values()} == {"default"}
        assert st["intrinsics_default"] is True
        assert "no calibration loaded: 3D reconstruction disabled" in st["warnings"]
        ss = c.j("GET", "/api/setup/status")[1]
        assert ss["calibration_loaded"] is False and ss["calibration_source"] == "default_intrinsics"
        assert ss["intrinsics_default"] is True
    finally:
        _shutdown(server, th)


def test_fixture_calibration_only_for_demo_or_bundled_fixture_sources(tmp_path):
    from hiveshot.pipeline import Pipeline
    from hiveshot.store import Store
    fx = [cfgmod.SourceConfig(cam_id=f"cam{i}", kind="file", target=f"fixtures/synth_basic/cam{i}.mp4")
          for i in (0, 1)]
    cfg = cfgmod.AppConfig(sources=fx, calibration_path=str(tmp_path / "none.json"))
    pl = Pipeline(cfg, Store(tmp_path / "1.db"), tmp_path, save_clips=False)
    st = pl.status()
    assert st["calibration_source"] == "fixture" and st["calibration_loaded"] is False
    pl.store.close()
    demo = Pipeline(cfg, Store(tmp_path / "2.db"), tmp_path, save_clips=False, demo=True)
    assert demo.status()["calibration_loaded"] is True       # the demo is a calibrated setup
    demo.store.close()
    # the same fixture videos copied somewhere else (a user's files): no borrowed calibration
    import shutil
    mine = tmp_path / "mine"
    mine.mkdir()
    for i in (0, 1):
        for suffix in (".mp4", "_truth.json"):
            shutil.copy(f"fixtures/synth_basic/cam{i}{suffix}", mine / f"cam{i}{suffix}")
    cfg2 = cfgmod.AppConfig(calibration_path=str(tmp_path / "none.json"), sources=[
        cfgmod.SourceConfig(cam_id=f"cam{i}", kind="file", target=str(mine / f"cam{i}.mp4"))
        for i in (0, 1)])
    pl2 = Pipeline(cfg2, Store(tmp_path / "3.db"), tmp_path, save_clips=False)
    assert pl2.calibration()[1] == {} and pl2.status()["calibration_source"] == "default_intrinsics"
    pl2.store.close()
    # any device/rtmp/url source with an otherwise bundled one: not a fixture setup
    mixed = cfg.model_copy(update={"sources": [fx[0], cfgmod.SourceConfig(
        cam_id="cam1", kind="device", target=0)]})
    pl3 = Pipeline(mixed, Store(tmp_path / "4.db"), tmp_path, save_clips=False)
    assert pl3.calibration()[1] == {}
    pl3.store.close()


def test_profile_intrinsics_slot_replaces_the_default(tmp_path):
    from hiveshot.pipeline import Pipeline
    from hiveshot.store import Store
    slot = {"width": 1920, "height": 1080, "fx": 905.0, "fy": 905.0, "cx": 961.0, "cy": 539.0,
            "dist": [-0.05, 0.01, 0.0, 0.0, 0.0]}
    cfg = cfgmod.AppConfig(
        calibration_path=str(tmp_path / "none.json"), active_profile="measured_arducam",
        profiles={"measured_arducam": {"intrinsics": slot}},
        sources=[cfgmod.SourceConfig(cam_id="a", kind="device", target=0),
                 cfgmod.SourceConfig(cam_id="b", kind="device", target=1)])
    pl = Pipeline(cfg, Store(tmp_path / "p.db"), tmp_path, save_clips=False)
    st = pl.status()
    assert pl.calibration()[0]["a"].fx == 905.0
    assert {v["intrinsics_source"] for v in st["cameras"].values()} == {"profile"}
    assert st["intrinsics_default"] is False
    assert not any("default lens intrinsics" in w for w in st["warnings"])
    pl.store.close()


def test_field_size_and_profile_slot_are_plain_config(client):
    cfg = client.j("GET", "/api/config")[1]
    assert cfg["active_profile"] is None
    s, j = client.j("PUT", "/api/config", {"active_profile": "arducam_1080p90"})
    assert s == 200 and j["active_profile"] == "arducam_1080p90"

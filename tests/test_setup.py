"""Setup wizard, tag-based auto-calibration, detector colour sampling, session housekeeping,
default config sections and HIVE-state-from-tags. Tag frames are rendered through the
virtual cameras (as in tests/test_tagkit.py) and served to the pipeline as looping videos."""

import csv
import json
import time

import cv2
import numpy as np
import pytest

from hiveshot import calib, ingest
from hiveshot import config as cfgmod
from hiveshot.app import create_app
from hiveshot.models import CameraIntrinsics
from hiveshot.pipeline import Pipeline
from hiveshot.store import Store
from tests.test_app import _serve, _shutdown
from tests.test_tagkit import _fixed_cams, _state, _vcam, render_tag_dict, render_tags

W, H = 1920, 1080


# ------------------------------------------------------------------------- helpers
def _video(path, frame, n=12):
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (W, H))
    assert vw.isOpened()
    for _ in range(n):
        vw.write(frame)
    vw.release()
    return str(path)


def _wait(pred, timeout=30.0, step=0.1):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(step)
    return pred()


class Rig:
    """An app serving two looping videos (one per virtual camera), calibrated or not."""

    def __init__(self, tmp_path, frames, with_extrinsics=False, cams=None, **cfg_kw):
        self.tmp = tmp_path
        self.cams = cams or {f"cam{i}": _vcam("gopro", k) for i, k in enumerate("AB")}
        self.data = tmp_path / "data"
        self.data.mkdir(exist_ok=True)
        calib.save_calibration(
            self.data / "calibration.json", [c.intr for c in self.cams.values()],
            [c.extr for c in self.cams.values()] if with_extrinsics else [])
        self.cfg_path = tmp_path / "config.json"
        self.cfg_kw = cfg_kw
        self.set_frames(frames)

    def set_frames(self, frames, tag="v"):
        srcs = [cfgmod.SourceConfig(
            cam_id=cid, kind="file", loop=True, realtime=True,
            target=_video(self.tmp / f"{tag}_{cid}.mp4", frames[cid]))
            for cid in self.cams]
        cfgmod.save(self.cfg_path, cfgmod.AppConfig(sources=srcs, **self.cfg_kw))

    def serve(self):
        self.server, self.th, self.c = _serve(create_app(self.cfg_path, self.data))
        return self.c

    def start(self):
        assert self.c.j("POST", "/api/pipeline/start")[0] == 200
        assert _wait(lambda: all(
            v["frames_read"] > 3 for v in self.c.j("GET", "/api/pipeline/status")[1]["cameras"].values()))

    def close(self):
        _shutdown(self.server, self.th)


@pytest.fixture()
def kit_rig(tmp_path):
    frames = {cid: render_tags(cam, seed=1) for cid, cam in
              ((f"cam{i}", _vcam("gopro", k)) for i, k in enumerate("AB"))}
    r = Rig(tmp_path, frames)
    c = r.serve()
    r.start()
    yield r, c
    r.close()


# ------------------------------------------------------------------ routes: tag kit
def test_tags_routes(client_plain):
    c = client_plain
    s, tags = c.j("GET", "/api/calib/tags")
    assert s == 200 and [t["id"] for t in tags] == [100, 101, 102, 103]
    assert set(tags[0]) >= {"id", "size_in", "name", "xyz_center", "corners_xyz"}
    s, h, body = c.get("/api/calib/tags.pdf")
    assert s == 200 and h["content-type"] == "application/pdf" and body.startswith(b"%PDF")


@pytest.fixture()
def client_plain(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfgmod.save(cfg_path, cfgmod.AppConfig())
    server, th, c = _serve(create_app(cfg_path, tmp_path / "data"))
    yield c
    _shutdown(server, th)


def test_auto_extrinsics_needs_frames_then_422_without_tags(client_plain):
    c = client_plain
    assert c.j("POST", "/api/calib/extrinsics/cam0/auto")[0] == 409       # not running
    assert c.j("POST", "/api/calib/extrinsics/nope/auto")[0] == 404
    assert c.j("POST", "/api/calib/auto_all")[0] == 409
    assert c.j("POST", "/api/pipeline/start")[0] == 200
    assert _wait(lambda: c.j("GET", "/api/pipeline/status")[1]["cameras"]["cam0"]["frames_read"] > 3)
    s, j = c.j("POST", "/api/calib/extrinsics/cam0/auto")
    assert s == 422 and "tag" in j["detail"]                             # fixture shows no tags
    s, j = c.j("POST", "/api/calib/auto_all")
    assert s == 200 and j["ok"] is False and j["crosscheck"] is None
    assert all(r["status"] == 422 for r in j["results"].values())


def test_auto_extrinsics_from_rendered_tags_and_crosscheck(kit_rig):
    r, c = kit_rig
    st = c.j("GET", "/api/pipeline/status")[1]
    assert st["calibration_loaded"] is False                             # intrinsics only
    s, one = c.j("POST", "/api/calib/extrinsics/cam0/auto")
    assert s == 200, one
    KIT = {100, 101, 102, 103}
    # how many kit tags a camera reads depends on the placement/frame geometry: at least two
    assert 2 <= len(one["tags_used"]) and set(one["tags_used"]) <= KIT
    assert one["reprojection_px"] < 1.5
    assert one["rmse_in"] < 0.5
    s, j = c.j("POST", "/api/calib/auto_all")
    assert s == 200 and j["ok"] is True, j
    assert j["max_error_in"] is not None and j["max_error_in"] < 1.0
    assert j["crosscheck"]["within_1_in"] is True
    both_seen = set(j["results"]["cam0"]["tags_used"]) & set(j["results"]["cam1"]["tags_used"])
    assert len(j["crosscheck"]["points"]) == 4 * len(both_seen)          # 4 corners per tag
    assert j["crosscheck"]["out_of_sample"] is False                     # no spare tag in view
    assert {p["name"] for p in j["crosscheck"]["points"]} >= {"tag 100 corner 0"}
    assert c.j("GET", "/api/pipeline/status")[1]["calibration_loaded"] is True
    # solved pose is close to the camera the frames were rendered with
    cal = c.j("GET", "/api/calib")[1]
    for e in cal["extrinsics"]:
        truth = r.cams[e["cam_id"]].extr
        R1 = cv2.Rodrigues(np.array(e["rvec"]))[0]
        R2 = cv2.Rodrigues(np.array(truth.rvec))[0]
        pos = lambda R, t: -R.T @ np.array(t)  # noqa: E731
        assert np.linalg.norm(pos(R1, e["tvec"]) - pos(R2, truth.tvec)) < 1.0
    # the standalone crosscheck route sees the stored tag clicks too
    assert c.j("POST", "/api/calib/crosscheck")[1]["within_1_in"] is True


def test_auto_extrinsics_source_modes(kit_rig):
    r, c = kit_rig
    assert c.j("POST", "/api/calib/extrinsics/cam0/auto", {"source": "bogus"})[0] == 422
    s, j = c.j("POST", "/api/calib/extrinsics/cam0/auto", {"source": "kit"})
    assert s == 200 and j["source"] == "kit" and j["warnings"] == [] and not j["hive_tags_used"]
    s, j = c.j("POST", "/api/calib/extrinsics/cam1/auto")           # default: both
    assert s == 200 and j["source"] == "both"
    assert 2 <= len(j["tags_used"]) and set(j["tags_used"]) <= {100, 101, 102, 103}
    assert j["warnings"] == []
    # "hive" with no HIVE tag in view: plain-language 422
    s, j = c.j("POST", "/api/calib/extrinsics/cam0/auto", {"source": "hive"})
    assert s == 422 and "tag" in j["detail"]


# ---------------------------------------------------------------- setup status
def test_setup_status_recommendations(client_plain, monkeypatch):
    c = client_plain
    monkeypatch.setattr(ingest, "list_devices", lambda max_index=10, **kw: [])
    s, j = c.j("GET", "/api/setup/status")
    assert s == 200
    assert set(j) == {"cameras_detected", "sources_configured", "calibration_loaded",
                      "calibration_source", "intrinsics_default",
                      "tags_seen", "tags_roll", "pipeline_running", "recommendations"}
    assert j["pipeline_running"] is False and j["cameras_detected"] == []
    assert j["calibration_loaded"] is False and j["calibration_source"] == "fixture"
    assert j["sources_configured"] is True
    # file fixtures and no camera on this PC: plug some in, and say the sources are files
    assert any(r.startswith("No cameras detected: plug in the cameras")
               for r in j["recommendations"])
    assert any("video files" in r and "Cameras step" in r for r in j["recommendations"])
    # a webcam is present: only the video-file advice remains
    monkeypatch.setattr(ingest, "list_devices", lambda max_index=10, **kw: [
        {"index": 0, "width": 1280, "height": 720, "fps": 30.0, "backend": "x"}])
    j = c.j("GET", "/api/setup/status")[1]
    assert j["cameras_detected"] == [{"index": 0, "width": 1280, "height": 720, "fps": 30.0}]
    assert not any("plug in" in r for r in j["recommendations"])
    assert any("video files" in r for r in j["recommendations"])
    monkeypatch.setattr(ingest, "list_devices", lambda max_index=10, **kw: [])
    # device sources, nothing detected, no calibration file
    c.j("PUT", "/api/config", {"sources": [
        {"cam_id": "cam0", "kind": "device", "target": 0},
        {"cam_id": "cam1", "kind": "device", "target": 1}],
        "calibration_path": "data/none.json"})
    j = c.j("GET", "/api/setup/status")[1]
    assert any(r.startswith("No cameras detected: plug in the cameras") for r in j["recommendations"])
    assert j["calibration_loaded"] is False
    assert any("print the tag sheet" in r and "Auto-calibrate" in r for r in j["recommendations"])
    # detected 1080p device at 30 fps while stopped
    monkeypatch.setattr(ingest, "list_devices", lambda max_index=10, **kw: [
        {"index": 0, "width": 1920, "height": 1080, "fps": 30.0, "backend": "x"}])
    j = c.j("GET", "/api/setup/status")[1]
    assert j["cameras_detected"] == [{"index": 0, "width": 1920, "height": 1080, "fps": 30.0}]
    assert any("camera 0 is at 30 fps" in r and "own USB port" in r for r in j["recommendations"])


def test_setup_status_flags_slow_running_camera(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    cfgmod.save(cfg_path, cfgmod.AppConfig(sources=[
        cfgmod.SourceConfig(cam_id="cam0", kind="device", target=0),
        cfgmod.SourceConfig(cam_id="cam1", kind="device", target=1)]))
    app = create_app(cfg_path, tmp_path / "data")
    pl = app.state.hs.pipeline
    real = pl.status()
    cams = {"cam0": {"fps": 31.4, "dropped": 0, "frames_read": 500, "is_alive": True,
                     "last_error": None, "props": {"width": 1920, "height": 1080, "fps": 90}},
            "cam1": {"fps": 88.0, "dropped": 0, "frames_read": 900, "is_alive": True,
                     "last_error": None, "props": {"width": 1920, "height": 1080, "fps": 90}}}
    pl.status = lambda: {**real, "running": True, "cameras": cams}
    probed = []
    monkeypatch.setattr(ingest, "_probe_one", lambda i, out: probed.append(i))
    server, th, c = _serve(app)
    try:
        j = c.j("GET", "/api/setup/status")[1]
        assert j["pipeline_running"] is True
        assert 0 not in probed and 1 not in probed        # indexes the pipeline holds are skipped
        slow = [r for r in j["recommendations"] if "is at 31 fps" in r]
        assert len(slow) == 1 and slow[0].startswith("camera cam0 is at 31 fps; move it to")
        assert "own USB port, not a shared hub" in slow[0]
        assert not any("camera cam1 is at" in r for r in j["recommendations"])
        assert [d["index"] for d in j["cameras_detected"]] == [0, 1]
    finally:
        _shutdown(server, th)


def test_setup_status_reports_tags_seen(kit_rig):
    r, c = kit_rig
    j = c.j("GET", "/api/setup/status")[1]
    assert j["pipeline_running"] is True
    # recommended poses: each camera sees the two kit tags on its own side of the frame
    # (more with the larger kit); ids are reported sorted
    seen = j["tags_seen"]
    assert set(seen) == {"cam0", "cam1"}
    for ids in seen.values():
        assert ids == sorted(ids) and set(ids) <= {100, 101, 102, 103}
    assert len(seen["cam0"]) >= 2 and len(seen["cam1"]) >= 2
    assert len(set(seen["cam0"]) | set(seen["cam1"])) >= 3
    assert any("Auto-calibrate" in x for x in j["recommendations"])


# ------------------------------------------------------------- detector colour sampling
def test_detector_sample_widens_range_persists_and_applies_live(client_plain):
    c = client_plain
    assert c.j("POST", "/api/detector/sample",
               {"cam_id": "cam0", "u": 10, "v": 10, "ball_type": "pollen"})[0] == 409
    assert c.j("POST", "/api/pipeline/start")[0] == 200
    assert _wait(lambda: c.j("GET", "/api/pipeline/status")[1]["cameras"]["cam0"]["frames_read"] > 3)
    base = {"cam_id": "cam0", "u": 960, "v": 540}
    assert c.j("POST", "/api/detector/sample", {**base, "ball_type": "banana"})[0] == 422
    assert c.j("POST", "/api/detector/sample", {**base, "u": 99999, "ball_type": "pollen"})[0] == 422
    assert c.j("POST", "/api/detector/sample", {**base, "cam_id": "zz", "ball_type": "pollen"})[0] == 404
    before = c.j("GET", "/api/config")[1]["detector"]
    s, j = c.j("POST", "/api/detector/sample", {**base, "ball_type": "nectar"})
    assert s == 200 and j["ball_type"] == "nectar"
    h, sa, v = j["sampled_hsv"]
    lo, hi = j["range"]
    old_lo, old_hi = before["nectar_hsv"]
    assert lo == [max(0, min(old_lo[0], h - 8)), max(0, min(old_lo[1], sa - 40)),
                  max(0, min(old_lo[2], v - 40))]
    assert hi == [min(179, max(old_hi[0], h + 8)), min(255, max(old_hi[1], sa + 40)),
                  min(255, max(old_hi[2], v + 40))]
    assert all(a <= b for a, b in zip(lo, old_lo, strict=True))        # only ever widens
    assert all(a >= b for a, b in zip(hi, old_hi, strict=True))
    after = c.j("GET", "/api/config")[1]["detector"]
    assert after["nectar_hsv"] == [lo, hi] and after["pollen_hsv"] == before["pollen_hsv"]


def test_detector_sample_applied_to_running_detectors(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfgmod.save(cfg_path, cfgmod.AppConfig())
    app = create_app(cfg_path, tmp_path / "data")
    server, th, c = _serve(app)
    try:
        c.j("POST", "/api/pipeline/start")
        assert _wait(lambda: c.j("GET", "/api/pipeline/status")[1]["cameras"]["cam0"]["frames_read"] > 3)
        s, j = c.j("POST", "/api/detector/sample",
                   {"cam_id": "cam0", "u": 500, "v": 300, "ball_type": "pollen"})
        assert s == 200
        want = (tuple(j["range"][0]), tuple(j["range"][1]))
        dets = app.state.hs.pipeline._detectors
        assert dets and all(d.det.cfg.pollen_hsv == want for d in dets.values())
    finally:
        _shutdown(server, th)


# ----------------------------------------------------------------- config defaults
def test_new_config_defaults_and_validation(client_plain):
    c = client_plain
    cfg = c.j("GET", "/api/config")[1]
    assert cfg["session_name_template"] == "Practice {date} {time}"
    assert cfg["session_idle_end_min"] == 10 and cfg["autosave_csv"] is True
    assert cfg["hive_tags_verified"] is False
    prof = cfg["profiles"]["arducam_1080p90"]["sources"]
    assert [(s["kind"], s["width"], s["height"], s["fps_hint"], s["backend"]) for s in prof] \
        == [("device", 1920, 1080, 90, "msmf")] * 2
    d = cfg["default_intrinsics"]["arducam_2.3mp_110"]
    assert (d["fx"], d["fy"], d["cx"], d["cy"], d["width"], d["height"]) == (771, 771, 960, 540, 1920, 1080)
    assert d["dist"] == [0, 0, 0, 0, 0]
    # a profile is a config patch: applying it through PUT works
    assert c.j("PUT", "/api/config", {"sources": prof})[0] == 200
    assert c.j("PUT", "/api/config", {"session_name_template": "{nope}"})[0] == 422
    assert c.j("PUT", "/api/config", {"session_idle_end_min": -1})[0] == 422


def test_session_name_template_used_for_new_sessions(client_plain):
    c = client_plain
    c.j("PUT", "/api/config", {"session_name_template": "Drill {date} @ {time}"})
    sid = c.j("POST", "/api/sessions")[1]["session_id"]
    name = next(s["name"] for s in c.j("GET", "/api/sessions")[1] if s["session_id"] == sid)
    assert name.startswith("Drill 20") and " @ " in name and "{" not in name
    assert cfgmod.format_session_name("Practice {date} {time}", 0.0).startswith("Practice 19")


def test_default_intrinsics_applied_with_warning(tmp_path):
    cfg = cfgmod.AppConfig(calibration_path=str(tmp_path / "missing.json"), sources=[
        cfgmod.SourceConfig(cam_id="a", kind="device", target=0),
        cfgmod.SourceConfig(cam_id="b", kind="device", target=1)])
    pl = Pipeline(cfg, Store(tmp_path / "d.db"), tmp_path, save_clips=False)
    intr, ext = pl.calibration()
    assert ext == {} and set(intr) == {"a", "b"}
    assert (intr["a"].fx, intr["a"].fy, intr["a"].cx, intr["a"].cy) == (771, 771, 960, 540)
    assert (intr["a"].width, intr["a"].height) == (1920, 1080) and set(intr["a"].dist) == {0.0}
    w = pl.status()["warnings"]
    assert any("camera a uses default lens intrinsics (fx 771): run the Lens step" in x for x in w)
    # a camera that has its own calibration keeps it, and gets no warning
    pl.store.close()
    calib.save_calibration(tmp_path / "c.json", [CameraIntrinsics("a", 1280, 720, 900, 900, 640, 360, (0,) * 5, 0.3)], [])
    cfg2 = cfg.model_copy(update={"calibration_path": str(tmp_path / "c.json")})
    pl2 = Pipeline(cfg2, Store(tmp_path / "e.db"), tmp_path, save_clips=False)
    assert pl2.calibration()[0]["a"].fx == 900 and pl2.calibration()[0]["b"].fx == 771
    w2 = pl2.status()["warnings"]
    assert not any("camera a uses default" in x for x in w2) and any("camera b uses default" in x for x in w2)
    pl2.store.close()
    off = Pipeline(cfg.model_copy(update={"default_intrinsics": {}}), Store(tmp_path / "f.db"),
                   tmp_path, save_clips=False)
    assert off.calibration()[0] == {}
    off.store.close()


# --------------------------------------------------------- idle end + CSV autosave
def _run_fixture(tmp_path, **kw):
    cfg = cfgmod.AppConfig(**kw, sources=[
        cfgmod.SourceConfig(cam_id=f"cam{i}", kind="file", target=f"fixtures/synth_basic/cam{i}.mp4",
                            realtime=False) for i in (0, 1)])
    store = Store(tmp_path / "p.db")
    events = []
    pl = Pipeline(cfg, store, tmp_path, on_event=events.append, save_clips=False)
    sid = store.create_session("Idle test")
    pl.set_session(sid)
    pl.start()
    assert _wait(pl.is_finished, 90)
    return cfg, store, pl, sid, events


@pytest.mark.parametrize("autosave", [True, False])
def test_idle_session_end_autosaves_csv_and_next_shot_starts_new_session(tmp_path, autosave):
    cfg, store, pl, sid, events = _run_fixture(tmp_path, autosave_csv=autosave)
    try:
        shots = store.list_shots(sid)
        assert len(shots) == 6 and sid in store.open_sessions()
        assert pl.session_id == sid                          # 10 min default: not idle yet
        pl.apply_config(cfg.model_copy(update={"session_idle_end_min": 0.02}))   # 1.2 s, live
        assert _wait(lambda: pl.status() and pl.session_id is None, 15)
        assert sid not in store.open_sessions()
        ended = [e for e in events if e["type"] == "session_ended"]
        assert len(ended) == 1 and ended[0]["session_id"] == sid and ended[0]["reason"] == "idle"
        exports = list((tmp_path / "exports").glob("*.csv")) if (tmp_path / "exports").exists() else []
        if autosave:
            assert len(exports) == 1 and sid in exports[0].name and "Idle_test" in exports[0].name
            with open(exports[0], newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            assert len(rows) == 6 and rows[0]["t_launch_wall"] != ""
            assert ended[0]["csv"] == str(exports[0])
        else:
            assert exports == [] and ended[0]["csv"] is None
        # the next shot after an idle end opens a fresh session named from the template
        pl.apply_config(pl._desired.model_copy(update={"session_idle_end_min": 10}))
        pl._finalize(shots[0].track)
        assert pl.session_id is not None and pl.session_id != sid
        names = {s["session_id"]: s["name"] for s in store.list_sessions()}
        assert names[pl.session_id].startswith("Practice 20")
        assert len(store.list_shots(pl.session_id)) == 1
    finally:
        pl.stop()
        store.close()


def test_user_ended_session_is_not_restarted_automatically(tmp_path):
    cfg, store, pl, sid, _ = _run_fixture(tmp_path)
    try:
        shots = store.list_shots(sid)
        pl.set_session(None)                                 # the user ended it
        pl._finalize(shots[0].track)
        assert pl.session_id is None
        assert len(store.list_shots("unassigned")) == 1
    finally:
        pl.stop()
        store.close()


# ---------------------------------------------------------------- HIVE state from tags
def test_infer_up_cell_from_visible_ids():
    f = Pipeline.infer_up_cell
    assert f([34, 35, 36], "red") == "audience"
    assert f([30, 31], "red") == "far"
    assert f([42, 43, 44], "blue") == "far"
    assert f([34, 30], "red") is None            # one tag each: unclear
    assert f([34, 35, 30, 31], "red") is None    # tie
    assert f([], "red") is None and f([38, 39], "red") is None   # other alliance's tags


def test_hive_state_source_stays_manual_by_default(client_plain):
    c = client_plain
    assert c.j("GET", "/api/pipeline/status")[1]["hive_state_source"] == "manual"
    c.j("POST", "/api/hive/state", {"alliance": "red", "up_cell": "far"})
    assert c.j("GET", "/api/pipeline/status")[1]["hive_state_source"] == "manual"


# ------------------------------------------------------------- learned HIVE tags
def test_learn_hive_tags_error_paths(client_plain):
    c = client_plain
    ok = {"state": {"alliance": "red", "up_cell": "audience"}}
    assert c.j("POST", "/api/calib/hive_tags/learn", {"state": {"alliance": "x"}})[0] == 422
    assert c.j("POST", "/api/calib/hive_tags/learn", ok)[0] == 409           # not running
    assert c.j("GET", "/api/calib/hive_tags")[1]["states"] == {}
    c.j("POST", "/api/pipeline/start")
    assert _wait(lambda: c.j("GET", "/api/pipeline/status")[1]["cameras"]["cam0"]["frames_read"] > 3)
    # no HIVE tag in view at all: "not visible from these cameras", not an error
    s, j = c.j("POST", "/api/calib/hive_tags/learn", ok)
    assert s == 200 and j["learned"] is False and j["learned_ids"] == []
    assert "not visible" in j["reason"] or "no HIVE tag" in j["reason"]
    assert j["complete"] is False                      # the audience-up state is not learned
    assert c.j("GET", "/api/calib/hive_tags")[1]["ready"] is False
    s, j = c.j("POST", "/api/calib/extrinsics/cam0/auto", {"use_hive_tags": True})
    assert s == 422                                           # no HIVE tags in the fixture


def test_tag_vote_hysteresis(tmp_path):
    pl = Pipeline(cfgmod.AppConfig(), Store(tmp_path / "v.db"), tmp_path, save_clips=False)
    pl._running = True
    pl.set_hive_state("red", "audience")
    t = 100.0
    pl._tag_vote("far", t)
    pl._tag_vote("far", t + 0.1)
    assert pl.hive_state().up_cell == "audience"                    # 2 votes: not yet
    pl._tag_vote("audience", t + 0.2)                               # disagreement resets
    pl._tag_vote("far", t + 0.3)
    pl._tag_vote("far", t + 0.4)
    assert pl.hive_state().up_cell == "audience"
    pl._tag_vote("far", t + 0.5)                                    # 3 votes over 0.2 s < 0.25 s
    assert pl.hive_state().up_cell == "audience"
    pl._tag_vote("far", t + 0.7)
    assert pl.hive_state().up_cell == "far"
    assert pl._hive_source == "tags" and len(pl.store.list_tips("unassigned")) == 1
    # a manual change wins until the tags confirm a state again
    pl.set_hive_state("red", "audience", source="manual")
    assert pl.hive_state_source() == "manual"
    for k in range(3):
        pl._tag_vote("audience", t + 2.0 + 0.2 * k)
    assert pl._manual_override is False and pl._hive_source == "tags"
    assert pl.hive_state().up_cell == "audience"
    pl.store.close()


def _world_cams(cams):
    return {"cam0": cams["A"], "cam1": cams["B"]}


def test_hive_tags_learn_and_follow_the_hive_state(tmp_path):
    """Generic tag rows (tests/test_tagkit.py's world) in both HIVE states: learn each state,
    then the pipeline follows the HIVE from the tags, logs the tip, and a manual override
    holds until the tags confirm a state again."""
    cams = _world_cams(_fixed_cams())
    frames = {up: {cid: render_tag_dict(cam, _state(up == "audience"), seed=7)
                   for cid, cam in cams.items()} for up in ("audience", "far")}
    rig = Rig(tmp_path, frames["audience"], with_extrinsics=True, cams=cams)
    c = rig.serve()
    try:
        rig.start()
        s, j = c.j("POST", "/api/calib/hive_tags/learn",
                   {"state": {"alliance": "red", "up_cell": "audience"}})
        assert s == 200, j
        assert j["learned_ids"] == [30, 31, 32, 33, 34, 35, 36, 37] and j["missing_ids"] == []
        assert j["max_residual_in"] < 1.0 and "up_cell_error_in" in j
        assert j["visible_per_camera"]["cam0"] == [30, 31, 32, 33, 34, 35, 36, 37]
        assert c.j("GET", "/api/calib/hive_tags")[1]["ready"] is False           # one state only
        got = np.array(json.loads((rig.data / "calibration.json").read_text())
                       ["hive_tags"]["red_audience"]["34"])
        assert np.abs(got - _state(True)[34]).max() < 1.0

        c.j("POST", "/api/pipeline/stop")                    # second state: far CELL up
        rig.set_frames(frames["far"], tag="far")
        assert c.j("PUT", "/api/config", json.loads(rig.cfg_path.read_text()))[0] == 200
        rig.start()
        s, j = c.j("POST", "/api/calib/hive_tags/learn",
                   {"state": {"alliance": "red", "up_cell": "far"}})
        assert s == 200 and j["max_residual_in"] < 1.0, j
        info = c.j("GET", "/api/calib/hive_tags")[1]
        assert info["ready"] is True and info["hive_state_source"] == "tags"
        assert set(info["states"]) == {"red_audience", "red_far"}
        rows = {k: v["row_height_in"] for k, v in info["states"].items()}
        assert rows["red_audience"]["red_audience"] == pytest.approx(50.2, abs=1.0)
        assert rows["red_far"]["red_audience"] == pytest.approx(35.0, abs=1.0)

        # the "far" renders are showing, the state started as "audience": tags correct it
        assert _wait(lambda: c.j("GET", "/api/pipeline/status")[1]["hive_state"]["up_cell"] == "far", 45)
        st = c.j("GET", "/api/pipeline/status")[1]
        assert st["hive_state_source"] == "tags"
        sid = st["session_id"]
        assert [t["new_up_cell"] for t in c.j("GET", f"/api/sessions/{sid}/tips")[1]] == ["far"]
        # a manual change wins until the tags confirm a state again
        assert c.j("POST", "/api/hive/state", {"alliance": "red", "up_cell": "audience"})[0] == 200
        assert c.j("GET", "/api/pipeline/status")[1]["hive_state_source"] == "manual"
        assert _wait(lambda: c.j("GET", "/api/pipeline/status")[1]["hive_state_source"] == "tags", 45)
        assert c.j("GET", "/api/pipeline/status")[1]["hive_state"]["up_cell"] == "far"
        saved = json.loads((rig.data / "calibration.json").read_text())
        assert set(saved["hive_tags"]) == {"red_audience", "red_far"}
        # roll sign per cluster in the setup status: audience cluster upside down (far up)
        roll = c.j("GET", "/api/setup/status")[1]["tags_roll"]["cam0"]
        assert roll["red_audience"]["sign"] == -1 and roll["red_far"]["sign"] == 1
    finally:
        rig.close()


def _computed_world():
    """Two zoomed cameras that see the CAD-computed audience-up CELL tags (ids 34-37)."""
    from hiveshot import field
    from hiveshot import placement as pl
    from hiveshot.synth import VirtualCamera
    tags = field.hive_tag_corners("red", "audience", field.HiveState("red", "audience"))
    ctr = np.mean([c.mean(axis=0) for c in tags.values()], axis=0)
    cams = {}
    for k, dx in (("cam0", -45.0), ("cam1", 45.0)):
        cams[k] = VirtualCamera(*pl.camera_from_pose((ctr[0] + dx, 100.0, 60.0), tuple(ctr), 40.0,
                                                    W, H, k))
    return cams, tags


def test_hive_tags_computed_positions_calibrate_without_the_kit(tmp_path):
    cams, tags = _computed_world()
    frames = {cid: render_tag_dict(cam, tags, seed=3) for cid, cam in cams.items()}
    rig = Rig(tmp_path, frames, with_extrinsics=True, cams=cams)
    c = rig.serve()
    try:
        rig.start()
        # no learning needed: the computed up-CELL geometry confirms the manual state
        assert _wait(lambda: c.j("GET", "/api/pipeline/status")[1]["hive_state_source"] == "tags", 45)
        assert c.j("GET", "/api/pipeline/status")[1]["hive_state"]["up_cell"] == "audience"
        roll = c.j("GET", "/api/setup/status")[1]["tags_roll"]
        assert roll["cam0"]["red_audience"]["sign"] == 1
        # learning compares the triangulated up-CELL tags with the CAD ones
        s, j = c.j("POST", "/api/calib/hive_tags/learn",
                   {"state": {"alliance": "red", "up_cell": "audience"}})
        assert s == 200 and j["learned_ids"] == [34, 35, 36, 37], j
        assert j["up_cell_error_in"] is not None and j["up_cell_error_in"] < 1.0
        # recalibrate from the HIVE tags alone (no printed kit)
        s, j = c.j("POST", "/api/calib/extrinsics/cam0/auto", {"source": "hive"})
        assert s == 200, j
        assert j["tags_used"] == [34, 35, 36, 37] and j["hive_tags_used"] is True
        assert j["reprojection_px"] < 2.0 and j["source"] == "hive"
        assert j["warnings"] == ["calibrated from HIVE tags only: expect 2-3x lower accuracy "
                                 "than the kit"]
        s, j = c.j("POST", "/api/calib/extrinsics/cam1/auto")             # default: both
        assert s == 200 and j["source"] == "both" and j["tags_used"] == [34, 35, 36, 37]
        assert j["warnings"] and "HIVE tags only" in j["warnings"][0]
        s, j = c.j("POST", "/api/calib/extrinsics/cam0/auto", {"source": "kit"})
        assert s == 422                                                    # the kit is not in view
        cal = c.j("GET", "/api/calib")[1]
        for e in cal["extrinsics"]:
            truth = cams[e["cam_id"]].extr
            R1, R2 = (cv2.Rodrigues(np.array(v))[0] for v in (e["rvec"], truth.rvec))
            d = np.linalg.norm(-R1.T @ np.array(e["tvec"]) + R2.T @ np.array(truth.tvec))
            assert d < 1.0, (e["cam_id"], d)
    finally:
        rig.close()


def test_hive_tags_with_a_single_tag_reading_camera(tmp_path):
    """Only one calibrated camera reads the up-CELL tags (the other has no view of them):
    the HIVE state still follows the tags, HIVE-tag calibration works for that camera, and
    the blind camera is refused with a plain-language 422."""
    cams, tags = _computed_world()
    frames = {"cam0": np.full((H, W, 3), 110, np.uint8),
              "cam1": render_tag_dict(cams["cam1"], tags, seed=3)}
    rig = Rig(tmp_path, frames, with_extrinsics=True, cams=cams)
    c = rig.serve()
    try:
        rig.start()
        assert _wait(lambda: c.j("GET", "/api/pipeline/status")[1]["hive_state_source"] == "tags", 45)
        assert c.j("GET", "/api/pipeline/status")[1]["hive_state"]["up_cell"] == "audience"
        seen = c.j("GET", "/api/setup/status")[1]["tags_seen"]
        assert seen["cam0"] == [] and seen["cam1"] == [34, 35, 36, 37]
        s, j = c.j("POST", "/api/calib/extrinsics/cam1/auto", {"source": "hive"})
        assert s == 200 and j["tags_used"] == [34, 35, 36, 37], j
        s, j = c.j("POST", "/api/calib/extrinsics/cam0/auto", {"source": "hive"})
        assert s == 422 and "HIVE tag" in j["detail"], j
        s, j = c.j("POST", "/api/calib/hive_tags/learn",
                   {"state": {"alliance": "red", "up_cell": "audience"}})
        assert s == 422                                      # learning needs both cameras
        s, j = c.j("POST", "/api/calib/auto_all", {"source": "hive"})
        assert s == 200 and j["ok"] is False
        assert j["results"]["cam1"]["ok"] is True and j["results"]["cam0"]["status"] == 422
    finally:
        rig.close()


def test_setup_status_lists_free_devices_and_flags_dropped_frames_while_running(
        tmp_path, monkeypatch):
    """File sources running + a webcam on the PC: the webcam is listed (probed through the
    cached ingest.list_devices) and recommendations come from the actual state, including
    dropped frames in the last minute."""
    cfg_path = tmp_path / "config.json"
    cfgmod.save(cfg_path, cfgmod.AppConfig(sources=[
        cfgmod.SourceConfig(cam_id=f"cam{i}", kind="file", target=f"fixtures/synth_basic/cam{i}.mp4",
                            loop=True) for i in (0, 1)]))
    calls = []

    def fake_list(max_index=10, **kw):
        calls.append(max_index)
        return [{"index": 0, "width": 1920, "height": 1080, "fps": 60.0, "backend": "x"}]

    monkeypatch.setattr(ingest, "list_devices", fake_list)
    app = create_app(cfg_path, tmp_path / "data")
    pl = app.state.hs.pipeline
    real = pl.status()
    cams = {c: {"fps": 60.0, "dropped": 0, "frames_read": 500, "is_alive": True,
                "last_error": None, "props": {"width": 1280, "height": 720, "fps": 60}}
            for c in ("cam0", "cam1")}
    state = {"cams": cams}
    pl.status = lambda: {**real, "running": True, "cameras": state["cams"]}
    server, th, c = _serve(app)
    try:
        j = c.j("GET", "/api/setup/status")[1]
        assert j["pipeline_running"] is True and calls
        assert j["cameras_detected"] == [{"index": 0, "width": 1920, "height": 1080, "fps": 60.0}]
        recs = j["recommendations"]
        assert any("video files" in r and "Cameras step" in r for r in recs)
        assert not any("plug in" in r or "dropping frames" in r for r in recs)
        # cam1 starts dropping frames
        state["cams"] = {**cams, "cam1": {**cams["cam1"], "dropped": 7}}
        recs = c.j("GET", "/api/setup/status")[1]["recommendations"]
        drop = [r for r in recs if "dropping frames" in r]
        assert len(drop) == 1 and drop[0].startswith("camera cam1 is dropping frames")
        assert "processing too slow" in drop[0] and "lower the preview fps" in drop[0]
        # the counter stays at 7: drops from before the window would not be flagged, so check
        # the window logic directly (older sample 61 s ago with the same count -> no drops)
        hs = app.state.hs
        with hs.lock:
            hs._drop_hist.clear()
            hs._drop_hist.append((time.monotonic() - 61.0, {"cam0": 0, "cam1": 7}))
        assert hs.recent_drops({**real, "running": True, "cameras": state["cams"]}) == {}
    finally:
        _shutdown(server, th)


# ------------------------------------------------- out-of-sample crosscheck (held-out tags)
@pytest.fixture()
def kit_and_hive_rig(tmp_path):
    """Two cameras on the audience side that both see kit tags (100 plus 103 / 102) and the
    computed HIVE tags of the current state (audience CELL up)."""
    from hiveshot import placement as pl
    from hiveshot import tagkit
    from hiveshot.field import HiveState
    from hiveshot.synth import VirtualCamera
    hive = tagkit.hive_tag_defs("red", HiveState("red", "audience"))
    cams = {f"cam{i}": VirtualCamera(*pl.camera_from_pose(pos, (0.0, 10.0, 30.0), 60.0, W, H,
                                                          f"cam{i}"))
            for i, pos in enumerate(((-30.0, 100.0, 60.0), (30.0, 100.0, 60.0)))}
    frames = {cid: render_tag_dict(cam, {**tagkit.tag_defs(), **hive}, seed=5)
              for cid, cam in cams.items()}
    rig = Rig(tmp_path, frames, cams=cams)
    c = rig.serve()
    rig.start()
    yield rig, c
    rig.close()


def test_crosscheck_holds_out_the_hive_tags_after_a_kit_solve(kit_and_hive_rig):
    r, c = kit_and_hive_rig
    for cam in ("cam0", "cam1"):
        s, j = c.j("POST", f"/api/calib/extrinsics/{cam}/auto", {"source": "kit"})
        assert s == 200 and all(100 <= t <= 103 for t in j["tags_used"]), j
    s, x = c.j("POST", "/api/calib/crosscheck")
    assert s == 200 and x["out_of_sample"] is True and x["held_out"] == "HIVE tags", x
    assert x["points"] and all(p["kind"] == "hive" and p["name"].startswith("hive tag ")
                               for p in x["points"])
    assert x["max_error_in"] == max(p["error_in"] for p in x["points"]) < 1.5
    assert set(x["points"][0]) >= {"name", "xyz_measured", "xyz_expected", "error_in"}


def test_crosscheck_never_uses_a_tag_either_solve_used(kit_and_hive_rig):
    """cam0 is solved from kit + HIVE tags, cam1 from the kit only: the HIVE tags were used by
    cam0's solve, so they are not held out (the answer falls back to the labelled in-sample
    re-measurement); with both cameras on the kit alone they are held out."""
    r, c = kit_and_hive_rig
    s, j0 = c.j("POST", "/api/calib/extrinsics/cam0/auto", {"source": "both"})
    assert s == 200 and any(t >= 30 and t < 100 for t in j0["tags_used"]), j0
    s, j1 = c.j("POST", "/api/calib/extrinsics/cam1/auto", {"source": "kit"})
    assert s == 200
    s, x = c.j("POST", "/api/calib/crosscheck")
    assert s == 200 and x["out_of_sample"] is False and "in-sample" in x["warning"], x
    assert all(p["name"].startswith("tag 1") for p in x["points"])        # the clicked kit corners
    s, j0 = c.j("POST", "/api/calib/extrinsics/cam0/auto", {"source": "kit"})
    assert s == 200
    x = c.j("POST", "/api/calib/crosscheck")[1]
    assert x["out_of_sample"] is True and x["held_out"] == "HIVE tags"


def test_auto_all_uses_the_kit_so_the_crosscheck_has_held_out_features(kit_and_hive_rig):
    r, c = kit_and_hive_rig
    s, j = c.j("POST", "/api/calib/auto_all")
    assert s == 200 and j["ok"] is True, j
    assert all(res["source"] == "kit" and not res["hive_tags_used"]
               for res in j["results"].values())
    xc = j["crosscheck"]
    assert xc["out_of_sample"] is True and xc["held_out"] == "HIVE tags"
    assert j["max_error_in"] == xc["max_error_in"] < 1.5


# ------------------------------------------- provenance, intrinsics gate, save gates, finish
def _patch_calibration_json(rig, fn):
    path = rig.data / "calibration.json"
    data = json.loads(path.read_text())
    fn(data)
    path.write_text(json.dumps(data))


def test_auto_all_reports_fit_residual_and_oos_error_and_provenance(kit_and_hive_rig):
    r, c = kit_and_hive_rig
    s, j = c.j("POST", "/api/calib/auto_all")
    assert s == 200 and j["ok"] is True, j
    for res in j["results"].values():
        assert res["fit_residual_in"] == res["rmse_in"]
        assert res["oos_error_in"] is not None and res["oos_error_in"] < 1.5   # HIVE tags held out
        assert res["intrinsics_default"] is False
    st = c.j("GET", "/api/pipeline/status")[1]
    assert st["calibration_source"] == "kit" and st["calibration_loaded"] is True
    assert {v["calibration_source"] for v in st["cameras"].values()} == {"kit"}
    assert {v["intrinsics_source"] for v in st["cameras"].values()} == {"measured"}
    saved = json.loads((r.data / "calibration.json").read_text())
    assert saved["intrinsics_source"] == {"cam0": "measured", "cam1": "measured"}
    assert saved["solve_tags"]["cam0"]["source"] == "kit"


def test_default_intrinsics_warning_and_flag_survive_saving_extrinsics(kit_and_hive_rig):
    r, c = kit_and_hive_rig
    c.j("POST", "/api/pipeline/stop")
    _patch_calibration_json(r, lambda d: d.update(intrinsics_source={"cam0": "default",
                                                                     "cam1": "default"}))
    k = r.cams["cam0"].intr                  # the "default" lens happens to equal the real one
    cfg = json.loads(r.cfg_path.read_text())
    cfg["default_intrinsics"] = {"arducam_2.3mp_110": {"width": k.width, "height": k.height, "fx": k.fx,
                                         "fy": k.fy, "cx": k.cx, "cy": k.cy, "dist": list(k.dist)}}
    assert c.j("PUT", "/api/config", cfg)[0] == 200
    r.start()
    st = c.j("GET", "/api/pipeline/status")[1]
    assert st["intrinsics_default"] is True
    assert any("default lens intrinsics (fx" in w and "run the Lens step" in w for w in st["warnings"])
    s, j = c.j("POST", "/api/calib/auto_all")
    assert s == 200 and j["ok"] is True, j
    assert all(res["intrinsics_default"] is True for res in j["results"].values())
    st = c.j("GET", "/api/pipeline/status")[1]                 # saved extrinsics did not clear it
    assert st["calibration_source"] == "kit" and st["intrinsics_default"] is True
    assert sum("default lens intrinsics" in w for w in st["warnings"]) == 2
    assert {v["intrinsics_source"] for v in st["cameras"].values()} == {"default"}
    saved = json.loads((r.data / "calibration.json").read_text())
    assert saved["intrinsics_source"] == {"cam0": "default", "cam1": "default"}
    # the wizard may not finish on default lenses, whatever the cross-check says
    s, j = c.j("POST", "/api/setup/finish")
    assert s == 409 and j["refused"] is True and "default lens intrinsics" in j["detail"]
    assert j["intrinsics_default_cameras"] == ["cam0", "cam1"]


def test_save_gate_refuses_a_resolution_mismatch(kit_and_hive_rig):
    r, c = kit_and_hive_rig
    c.j("POST", "/api/pipeline/stop")

    def small(d):
        for i in d["intrinsics"]:
            i["width"], i["height"] = 1280, 720
    _patch_calibration_json(r, small)
    assert c.j("PUT", "/api/config", json.loads(r.cfg_path.read_text()))[0] == 200
    r.start()
    s, j = c.j("POST", "/api/calib/extrinsics/cam0/auto", {"source": "kit"})
    assert s == 409 and j["refused"] is True
    assert j["frame_size"] == [1920, 1080] and j["intrinsics_size"] == [1280, 720]
    assert "1920x1080" in j["detail"] and "not saved" in j["detail"]
    assert c.j("GET", "/api/calib")[1]["extrinsics"] == []


def test_save_gate_refuses_a_high_reprojection_error(kit_and_hive_rig, monkeypatch):
    r, c = kit_and_hive_rig
    real = calib.solve_extrinsics_from_tags

    def bad(*a, **k):
        ext, info = real(*a, **k)
        return ext, {**info, "reprojection_px": 6.5}
    monkeypatch.setattr(calib, "solve_extrinsics_from_tags", bad)
    s, j = c.j("POST", "/api/calib/extrinsics/cam0/auto", {"source": "kit"})
    assert s == 409 and j["reprojection_px"] == 6.5 and "6.5 px" in j["detail"]
    assert c.j("GET", "/api/calib")[1]["extrinsics"] == []
    monkeypatch.setattr(calib, "solve_extrinsics_from_tags", real)
    assert c.j("POST", "/api/calib/extrinsics/cam0/auto", {"source": "kit"})[0] == 200


def test_save_gate_refuses_a_big_out_of_sample_error(kit_and_hive_rig):
    """The HIVE state is set the wrong way round, so the held-out HIVE tags are ~15 in away
    from where the model says they are: the kit solve is right, the check says otherwise."""
    r, c = kit_and_hive_rig
    assert c.j("POST", "/api/hive/state", {"alliance": "red", "up_cell": "far"})[0] == 200
    s, j = c.j("POST", "/api/calib/extrinsics/cam0/auto", {"source": "kit"})
    assert s == 409 and j["oos_error_in"] > 2.0 and "not used for the solve" in j["detail"]
    assert c.j("GET", "/api/calib")[1]["extrinsics"] == []
    assert c.j("POST", "/api/hive/state", {"alliance": "red", "up_cell": "audience"})[0] == 200
    assert c.j("POST", "/api/calib/extrinsics/cam0/auto", {"source": "kit"})[0] == 200


def test_setup_finish_gate(kit_and_hive_rig):
    r, c = kit_and_hive_rig
    s, j = c.j("POST", "/api/setup/finish")
    assert s == 409 and j["refused"] is True and "cross-check could not run" in j["detail"]
    assert c.j("POST", "/api/calib/auto_all")[0] == 200
    s, j = c.j("POST", "/api/setup/finish")
    assert s == 200 and j["ok"] is True and j["out_of_sample"] is True
    assert j["max_error_in"] <= 1.0 and j["calibration_source"] == "kit"


def test_learn_with_nothing_visible_finishes_when_the_audience_state_is_known(tmp_path):
    frames = {cid: render_tags(cam, seed=1) for cid, cam in
              ((f"cam{i}", _vcam("gopro", k)) for i, k in enumerate("AB"))}
    rig = Rig(tmp_path, frames, with_extrinsics=True)
    _patch_calibration_json(rig, lambda d: d.update(hive_tags={"red_audience": {
        "34": [[0.0, 0.0, 0.0]] * 4}}))
    c = rig.serve()
    try:
        rig.start()
        far = {"state": {"alliance": "red", "up_cell": "far"}}
        s, j = c.j("POST", "/api/calib/hive_tags/learn", far)
        assert s == 200 and j["learned"] is False and j["learned_ids"] == []
        assert j["complete"] is True and "not visible" in j["reason"] or "no HIVE tag" in j["reason"]
        assert j["missing_ids"] and j["visible_per_camera"] == {"cam0": [], "cam1": []}
    finally:
        rig.close()

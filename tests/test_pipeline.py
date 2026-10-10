import json
import logging
import threading
import time
from pathlib import Path

import pytest

from hiveshot import calib
from hiveshot import config as cfgmod
from hiveshot import pipeline as pipemod
from hiveshot.models import CameraExtrinsics, CameraIntrinsics, TipEvent
from hiveshot.pipeline import Pipeline
from hiveshot.stats import compute_stats
from hiveshot.store import Store

FIX = Path(__file__).resolve().parent.parent / "fixtures" / "synth_basic"
FIX_BURST = FIX.parent / "synth_burst"

try:
    import hiveshot.detect  # noqa: F401
    import hiveshot.recon  # noqa: F401
    import hiveshot.track2d  # noqa: F401
    HAVE_MODULES = True
except ImportError:
    HAVE_MODULES = False


def _made(t):
    return bool(t["made"] if "made" in t else t["made_truth"])


@pytest.mark.xfail(not HAVE_MODULES, reason="detect/track2d/recon not present yet", strict=False)
def test_pipeline_on_synth_fixture(tmp_path):
    cfg = cfgmod.AppConfig()
    for s in cfg.sources:
        s.realtime = False
    store = Store(tmp_path / "p.db")
    events = []
    pl = Pipeline(cfg, store, tmp_path, on_event=events.append, save_clips=False)
    sid = store.create_session("fixture")
    pl.set_session(sid)
    pl.start()
    try:
        deadline = time.time() + 60
        while time.time() < deadline and not pl.is_finished():
            time.sleep(0.2)
        assert pl.is_finished(), "pipeline did not consume both files within 60 s"
        st = pl.status()
    finally:
        pl.stop()
    assert set(st["cameras"]) == {"cam0", "cam1"}
    assert st["cameras"]["cam0"]["frames_read"] > 100

    truth = json.loads((FIX / "shots.json").read_text())
    n_made = sum(1 for t in truth if _made(t))
    shots = store.list_shots(sid)
    assert len(shots) == len(truth)
    assert sum(s.result.value == "made" for s in shots) == n_made
    for s in shots:
        assert s.exit_speed_ips and s.exit_speed_ips > 0
        assert s.parabola is not None
    # fixture shots are launched 0.25 s apart: one burst, indices run 1..N
    offsets = sorted(t.get("t_launch", t.get("t_offset")) for t in truth)
    if all(b - a <= 1.5 for a, b in zip(offsets, offsets[1:], strict=False)):
        assert max(s.burst_index for s in shots) >= 2
        assert len({s.burst_id for s in shots}) == 1
    types = [e["type"] for e in events]
    assert types.count("shot") == len(shots) and "stats" in types
    store.close()


def _run_fixture(fixture: str, tmp_path, **cfg_kw):
    cfg = cfgmod.AppConfig(**cfg_kw, sources=[
        cfgmod.SourceConfig(cam_id=f"cam{i}", kind="file",
                            target=f"fixtures/{fixture}/cam{i}.mp4", realtime=False)
        for i in (0, 1)])
    store = Store(tmp_path / "p.db")
    pl = Pipeline(cfg, store, tmp_path, save_clips=False)
    sid = store.create_session("fixture")
    pl.set_session(sid)
    pl.start()
    try:
        deadline = time.time() + 90
        while time.time() < deadline and not pl.is_finished():
            time.sleep(0.2)
        assert pl.is_finished(), "pipeline did not consume both files within 90 s"
    finally:
        pl.stop()
    return store, sid, pl


@pytest.mark.xfail(not HAVE_MODULES, reason="detect/track2d/recon not present yet", strict=False)
def test_pipeline_on_burst_fixture(tmp_path):
    truth = sorted(json.loads((FIX_BURST / "shots.json").read_text()),
                   key=lambda t: t["t_launch"])
    assert len(truth) == 6
    store, sid, pl = _run_fixture("synth_burst", tmp_path)
    try:
        shots = sorted(store.list_shots(sid), key=lambda s: s.t_launch)
        assert len(shots) == 6
        assert sum(s.result.value == "made" for s in shots) == sum(_made(t) for t in truth)
        assert [(s.burst_id, s.burst_index) for s in shots] == [
            (1, 1), (1, 2), (1, 3), (1, 4), (2, 1), (2, 2)]
        # misses land at the truth burst indexes (1-based position inside the burst)
        expected = {k: 0 for k in range(1, 6)}
        bursts = [truth[:4], truth[4:]]
        for burst in bursts:
            for i, t in enumerate(burst, start=1):
                if not _made(t):
                    expected[min(i, 5)] += 1
        stats = compute_stats(shots, [], sid)
        assert stats.failure_order_hist == expected
        assert sum(expected.values()) == 2
        for s, t in zip(shots, truth, strict=True):
            assert s.exit_speed_ips == pytest.approx(t["speed_ips"], rel=0.03)
            assert s.apex_z_in == pytest.approx(t["apex_z_in"], abs=2.0)
        # no fragment stitching is needed on this fixture; shots are finalized promptly
        assert all(rec["fragments"] == 1 for rec in pl.finalize_log)
    finally:
        store.close()


@pytest.mark.xfail(not HAVE_MODULES, reason="detect/track2d/recon not present yet", strict=False)
def test_stitching_disabled_gives_same_shots(tmp_path):
    store, sid, pl = _run_fixture("synth_basic", tmp_path, stitch_gap_s=0.0)
    try:
        shots = store.list_shots(sid)
        assert len(shots) == 6
        assert sum(s.result.value == "made" for s in shots) == 4
        # promptness: finalized within ~finalize_delay_s + one recon cycle of source time
        lags = [r["since_closed_s"] for r in pl.finalize_log]
        assert max(lags) < 1.2
    finally:
        store.close()


# --------------------------------------------------------------------------- helpers
def _file_cfg(fixture="synth_basic", **kw):
    return cfgmod.AppConfig(**kw, sources=[
        cfgmod.SourceConfig(cam_id=f"cam{i}", kind="file",
                            target=f"fixtures/{fixture}/cam{i}.mp4", realtime=False)
        for i in (0, 1)])


def _wait(pred, timeout, step=0.05):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(step)
    return pred()


def _truth_basic():
    return sorted(json.loads((FIX / "shots.json").read_text()), key=lambda t: t["t_launch"])


def _names(prefix):
    return [t for t in threading.enumerate() if t.name.startswith(prefix)]


# ------------------------------------------------------------------------- F1 tips
@pytest.mark.xfail(not HAVE_MODULES, reason="detect/track2d/recon not present yet", strict=False)
def test_made_shot_that_tips_hive_stays_made_and_links_tip(tmp_path):
    """The HIVE flips 0.3 s after shot 1 enters the cell. The shot must still be MADE
    (classified with the state at its launch) and the tip must point at it."""
    store = Store(tmp_path / "p.db")
    pl = Pipeline(_file_cfg(), store, tmp_path, save_clips=False)
    sid = store.create_session("tip")
    pl.set_session(sid)
    orig = pl._finalize
    flipped = {}

    def hooked(tr3, chain=None):
        if not flipped:
            flipped["t_launch"] = tr3.points[0].t
            flipped["t"] = tr3.points[-1].t + 0.3
            pl.set_hive_state("red", "far", t=flipped["t"])
        return orig(tr3, chain)

    pl._finalize = hooked
    pl.start()
    try:
        assert _wait(pl.is_finished, 90), "pipeline did not finish"
    finally:
        pl.stop()
    try:
        shots = sorted(store.list_shots(sid), key=lambda s: s.t_launch)
        first = shots[0]
        assert first.t_launch == pytest.approx(flipped["t_launch"])
        assert first.result.value == "made", "tipping shot recorded as a miss"
        tips = store.list_tips(sid)
        assert len(tips) == 1 and tips[0].new_up_cell == "far"
        assert tips[0].caused_by_shot_id == first.shot_id
    finally:
        store.close()


def test_hive_state_history_lookup(tmp_path):
    pl = Pipeline(cfgmod.AppConfig(), Store(tmp_path / "h.db"), tmp_path, save_clips=False)
    pl.set_hive_state("red", "far", t=5.0)
    pl.set_hive_state("red", "audience", t=9.0)
    assert pl._state_at(1.0).up_cell == "audience"
    assert pl._state_at(5.0).up_cell == "far"
    assert pl._state_at(8.9).up_cell == "far"
    assert pl._state_at(9.0).up_cell == "audience"
    pl.store.close()


def test_link_tips_requires_window_and_entry(tmp_path):
    store = Store(tmp_path / "p.db")
    pl = Pipeline(cfgmod.AppConfig(), store, tmp_path, save_clips=False)
    sid = store.create_session("l")
    shot = type("S", (), {"t_launch": 10.0, "session_id": sid, "shot_id": 1})()
    # (tip time, expected cause): before launch -> no; ball entered at 10.4 -> yes;
    # beyond launch + 3 s -> no; before the ball entered the cell (10.1 < 10.4 - 0.15) -> no
    for t, expect in ((9.0, None), (10.5, 1), (13.5, None), (10.1, None)):
        tip = TipEvent(t, sid, "red", "far", None)
        tid = store.add_tip(tip)
        pl._pending_tips = [pipemod._PendingTip(tid, tip)]
        pl._link_tips(shot, 10.4)
        assert store.list_tips(sid)[-1].caused_by_shot_id == expect, t
        store.set_tip_cause(tid, None)
    store.close()


# ------------------------------------------------------------------- F2 lifecycle
@pytest.mark.xfail(not HAVE_MODULES, reason="detect/track2d/recon not present yet", strict=False)
def test_concurrent_start_creates_one_set_of_threads(tmp_path):
    store = Store(tmp_path / "p.db")
    pl = Pipeline(_file_cfg(), store, tmp_path, save_clips=False)
    barrier = threading.Barrier(4)
    results = []

    def go():
        barrier.wait()
        results.append(pl.start())

    ths = [threading.Thread(target=go) for _ in range(4)]
    try:
        for t in ths:
            t.start()
        for t in ths:
            t.join(30)
        assert len(results) == 4 and all(r["running"] for r in results)
        assert len(_names("cam-")) == 2 and len(_names("lockstep-")) == 2
        assert len(_names("recon")) == 1
    finally:
        pl.stop()
        pl.stop()                                # second stop is a no-op
    assert not pl.running
    assert _names("cam-") == [] and _names("recon") == []
    store.close()


# ----------------------------------------------------------------- F6 stop flushes
@pytest.mark.xfail(not HAVE_MODULES, reason="detect/track2d/recon not present yet", strict=False)
def test_stop_mid_fixture_flushes_completed_shots(tmp_path):
    truth = _truth_basic()
    store = Store(tmp_path / "p.db")
    pl = Pipeline(_file_cfg(), store, tmp_path, save_clips=False)
    sid = store.create_session("stop")
    pl.set_session(sid)
    pl.start()
    try:
        assert _wait(lambda: (pl.status()["last_shot_id"] or 0) >= 2, 60)
        t_pre = pl._clock()                       # both cameras have reached at least this
    finally:
        pl.stop()
    try:
        # truth shots whose whole flight (launch + duration) lies before the time both
        # cameras had reached when stop was requested must all be stored by the flush
        complete = [t for t in truth if t["t_launch"] + t["duration_s"] <= t_pre - 0.1]
        assert len(complete) >= 2
        stored = store.list_shots(sid)
        for t in complete:
            assert any(abs(s.t_launch - t["t_launch"]) < 0.15 for s in stored), \
                f"completed shot launched at {t['t_launch']} lost on stop (t_pre={t_pre:.2f})"
        assert not _names("cam-") and not _names("recon")
    finally:
        store.close()


# ------------------------------------------------------------------ F8 calibration
@pytest.mark.xfail(not HAVE_MODULES, reason="detect/track2d/recon not present yet", strict=False)
def test_calibration_size_mismatch_reported(tmp_path):
    intr, ext = [], []
    for cam in ("cam0", "cam1"):
        d = json.loads((FIX / f"{cam}_truth.json").read_text())
        intr.append(CameraIntrinsics(**{**d["intrinsics"], "cam_id": cam, "width": 1280,
                                        "height": 720, "dist": tuple(d["intrinsics"]["dist"])}))
        ext.append(CameraExtrinsics(**{**d["extrinsics"], "cam_id": cam,
                                       "rvec": tuple(d["extrinsics"]["rvec"]),
                                       "tvec": tuple(d["extrinsics"]["tvec"])}))
    cal = tmp_path / "wrong_size.json"
    calib.save_calibration(cal, intr, ext)
    store = Store(tmp_path / "p.db")
    pl = Pipeline(_file_cfg(calibration_path=str(cal)), store, tmp_path, save_clips=False)
    assert pl.status()["calibration_mismatch"] == {}
    pl.start()
    try:
        assert _wait(lambda: len(pl.status()["calibration_mismatch"]) == 2, 30)
        assert pl.status()["calibration_mismatch"] == {
            "cam0": "1280x720 vs 1920x1080", "cam1": "1280x720 vs 1920x1080"}
    finally:
        pl.stop()
        store.close()


@pytest.mark.xfail(not HAVE_MODULES, reason="detect/track2d/recon not present yet", strict=False)
def test_matching_calibration_reports_no_mismatch(tmp_path):
    store = Store(tmp_path / "p.db")
    pl = Pipeline(_file_cfg(), store, tmp_path, save_clips=False)
    pl.start()
    try:
        assert _wait(lambda: len(pl._frame_size) == 2, 30)
        assert pl.status()["calibration_mismatch"] == {}
    finally:
        pl.stop()
        store.close()


# ------------------------------------------------------------- F10 stalled camera
def test_clock_ignores_stalled_camera(tmp_path):
    pl = Pipeline(cfgmod.AppConfig(), Store(tmp_path / "c.db"), tmp_path, save_clips=False)
    now = time.monotonic()
    pl._done = {"cam0": False, "cam1": False}
    pl._cam_t = {"cam0": 10.0, "cam1": 3.0}
    pl._cam_wall = {"cam0": now, "cam1": now}
    assert pl._clock() == 3.0                    # both live: the slowest
    pl._cam_wall["cam1"] = now - pipemod.STALL_AFTER_S - 1.0
    assert pl._clock() == 10.0                   # cam1 stalled: ignored
    pl._cam_wall["cam0"] = now - 30
    pl._last_t = 10.0
    assert pl._clock() == 10.0                   # everything stalled: latest time seen
    pl.store.close()


@pytest.mark.xfail(not HAVE_MODULES, reason="detect/track2d/recon not present yet", strict=False)
def test_stalled_camera_does_not_block_finalization(tmp_path, monkeypatch):
    """cam1's reader hangs (no frames, not finished) after 120 frames (t = 2.0 s). Shots
    that ended well before the end must still be finalized, which needs the clock to follow
    cam0 once cam1 is detected as stalled."""
    orig_get = pipemod._LockstepReader.get
    delivered = {"n": 0}

    def get(self, timeout=None):
        if self.spec.cam_id == "cam1":
            if delivered["n"] >= 120:
                time.sleep(0.05)
                return None
            fr = orig_get(self, timeout)
            delivered["n"] += fr is not None
            return fr
        return orig_get(self, timeout)

    monkeypatch.setattr(pipemod._LockstepReader, "get", get)
    truth = _truth_basic()
    store = Store(tmp_path / "p.db")
    pl = Pipeline(_file_cfg(), store, tmp_path, save_clips=False)
    sid = store.create_session("stall")
    pl.set_session(sid)
    pl.start()
    try:
        want = [t for t in truth if t["t_launch"] + t["duration_s"] <= 1.8]
        assert len(want) >= 4
        assert _wait(lambda: len(store.list_shots(sid)) >= len(want), 25), \
            f"only {len(store.list_shots(sid))} of {len(want)} shots finalized while cam1 stalled"
        assert not pl.is_finished()
    finally:
        pl.stop()
        store.close()


@pytest.mark.xfail(not HAVE_MODULES, reason="detect/track2d/recon not present yet", strict=False)
def test_unavailable_device_source_does_not_wedge_pipeline(tmp_path):
    cfg = cfgmod.AppConfig(sources=[
        cfgmod.SourceConfig(cam_id="cam0", kind="file", target="fixtures/synth_basic/cam0.mp4",
                            realtime=False),
        cfgmod.SourceConfig(cam_id="cam1", kind="device", target=99, backend="auto")])
    store = Store(tmp_path / "p.db")
    pl = Pipeline(cfg, store, tmp_path, save_clips=False)
    pl.start()
    try:
        assert _wait(lambda: pl._cam_t.get("cam0", 0.0) > 1.0, 30)
        assert pl._clock() > 1.0                  # follows cam0, not stuck at 0
        assert pl.status()["cameras"]["cam1"]["frames_read"] == 0
    finally:
        t0 = time.time()
        pl.stop()
        assert time.time() - t0 < 15
        store.close()


# ------------------------------------------------------------------- F12 sessions
@pytest.mark.xfail(not HAVE_MODULES, reason="detect/track2d/recon not present yet", strict=False)
def test_shots_without_active_session_go_to_unassigned(tmp_path, caplog):
    store = Store(tmp_path / "p.db")
    pl = Pipeline(_file_cfg(), store, tmp_path, save_clips=False)
    caplog.set_level(logging.WARNING, logger="hiveshot.pipeline")
    pl.start()
    sid = pl.status()["session_id"]
    assert sid is not None and store.session_exists(sid)     # start opens a session
    pl.set_session(None)                                      # user ended it
    assert pl.status()["session_id"] is None
    try:
        assert _wait(pl.is_finished, 90)
    finally:
        pl.stop()
    try:
        assert store.list_shots(sid) == []
        assert len(store.list_shots("unassigned")) == 6
        warnings = [r for r in caplog.records if "no active session" in r.getMessage()]
        assert len(warnings) == 1
        assert "unassigned" not in store.open_sessions()
    finally:
        store.close()


# ------------------------------------------------------------------ F3 live config
def test_apply_config_rejects_source_change_while_running(tmp_path):
    store = Store(tmp_path / "p.db")
    cfg = _file_cfg()
    pl = Pipeline(cfg, store, tmp_path, save_clips=False)
    pl.start()
    try:
        swapped = cfg.model_copy(update={"sources": list(reversed(cfg.sources))})
        with pytest.raises(pipemod.ConfigConflict):
            pl.apply_config(swapped)
        new = cfg.model_copy(update={"burst_gap_s": 2.5, "finalize_delay_s": 0.7,
                                     "hive_up_cell": "far"})
        assert pl.apply_config(new) == []
        assert pl._rcfg.burst_gap_s == 2.5 and pl._rcfg.finalize_delay_s == 0.7
        assert pl.hive_state().up_cell == "far"
        assert [s.cam_id for s in pl._rcfg.sources] == ["cam0", "cam1"]
        det = new.model_copy(update={"detector": cfgmod.DetectorSection(min_radius_px=9)})
        assert pl.apply_config(det) == ["detector"]
    finally:
        pl.stop()
        store.close()


# --------------------------------------------------------------- F4 burst updates
@pytest.mark.xfail(not HAVE_MODULES, reason="detect/track2d/recon not present yet", strict=False)
def test_burst_changes_are_broadcast_consistently(tmp_path):
    events = []
    store = Store(tmp_path / "p.db")
    pl = Pipeline(_file_cfg("synth_burst"), store, tmp_path, on_event=events.append,
                  save_clips=False)
    sid = store.create_session("b")
    pl.set_session(sid)
    pl.start()
    try:
        assert _wait(pl.is_finished, 90)
    finally:
        pl.stop()
    try:
        latest = {}
        for e in events:
            if e["type"] in ("shot", "shot_updated"):
                latest[e["shot"]["shot_id"]] = (e["shot"]["burst_id"], e["shot"]["burst_index"])
        stored = {s.shot_id: (s.burst_id, s.burst_index) for s in store.list_shots(sid)}
        assert len(stored) == 6 and latest == stored      # clients end up with the DB state
        assert all(s.notes.count("burst exceeds") <= 1 for s in store.list_shots(sid))
    finally:
        store.close()


# ------------------------------------------------ mid-air tracks, dropped frames, timing
def _cut_stream_after(n_frames):
    """Patch for _LockstepReader.get: each camera ends (cleanly) after n_frames frames."""
    orig = pipemod._LockstepReader.get
    count = {}

    def get(self, timeout=None):
        k = self.spec.cam_id
        if count.get(k, 0) >= n_frames:
            self.finished = True
            return None
        fr = orig(self, timeout)
        count[k] = count.get(k, 0) + (fr is not None)
        return fr
    return get


@pytest.mark.xfail(not HAVE_MODULES, reason="detect/track2d/recon not present yet", strict=False)
def test_stream_cut_mid_flight_gives_unknown_not_miss(tmp_path, monkeypatch):
    """The end-of-stream flush must not call a ball that is still in the air a MISS."""
    monkeypatch.setattr(pipemod._LockstepReader, "get", _cut_stream_after(100))   # t = 1.65 s
    store, sid, pl = _run_fixture("synth_basic", tmp_path)
    try:
        shots = store.list_shots(sid)
        assert shots
        for s in shots:
            last = s.track.points[-1]
            if s.result.value == "miss":
                assert last.z <= 10.0 or min(p.z for p in s.track.points[-5:]) < 53.0, \
                    f"mid-air track at z={last.z:.0f} classified as a miss"
        unknown = [s for s in shots if s.result.value == "unknown"]
        assert unknown, [(s.result.value, s.track.points[-1].z) for s in shots]
        assert all("track lost" in s.notes for s in unknown)
    finally:
        store.close()


@pytest.mark.xfail(not HAVE_MODULES, reason="detect/track2d/recon not present yet", strict=False)
def test_dropped_frames_are_flagged_on_shots_in_flight(tmp_path, monkeypatch):
    orig = pipemod._LockstepReader.get

    def get(self, timeout=None):
        fr = orig(self, timeout)
        while fr is not None and 60 <= fr.frame_idx < 66:     # 6 frames lost, t = 1.0-1.1 s
            fr = orig(self, timeout)
        return fr

    monkeypatch.setattr(pipemod._LockstepReader, "get", get)
    events = []
    store = Store(tmp_path / "p.db")
    pl = Pipeline(_file_cfg(), store, tmp_path, on_event=events.append, save_clips=False)
    sid = store.create_session("drops")
    pl.set_session(sid)
    pl.start()
    try:
        assert _wait(pl.is_finished, 90)
    finally:
        pl.stop()
    try:
        shots = store.list_shots(sid)
        flagged = [s for s in shots if "frames dropped during flight" in s.notes]
        assert flagged, "no shot carries the dropped-frames note"
        for s in flagged:
            t0, t1 = s.track.points[0].t, s.track.points[-1].t
            assert t0 < 1.1 and t1 + 0.05 > 0.98, "flagged shot was not in flight during the loss"
            n = int(s.notes.split("frames dropped during flight (")[1].split(")")[0])
            assert n == 12      # 6 frames on each of the two cameras
        sums = {e["shot"]["shot_id"]: e["shot"]["dropped_during_flight"]
                for e in events if e["type"] == "shot"}
        assert any(v == 12 for v in sums.values())
        assert all(v == 0 for k, v in sums.items() if k not in {s.shot_id for s in flagged})
    finally:
        store.close()


@pytest.mark.xfail(not HAVE_MODULES, reason="detect/track2d/recon not present yet", strict=False)
def test_no_drops_means_no_note_and_status_reports_timing(tmp_path):
    store, sid, pl = _run_fixture("synth_basic", tmp_path)
    try:
        assert all("dropped" not in s.notes for s in store.list_shots(sid))
        tm = pl.status()["timing"]
        assert set(tm) == {"detect_ms", "track_ms", "preview_ms", "ring_ms", "recon_ms",
                           "offset_s", "offset_confidence"}
        assert tm["offset_s"] == pytest.approx(0.0, abs=0.01)
        assert tm["detect_ms"] > 0 and tm["track_ms"] >= 0 and tm["recon_ms"] > 0
        assert tm["preview_ms"] == 0.0 and tm["ring_ms"] == 0.0   # no client, clips off
        assert set(pl.status()["timing_per_camera"]) == {"cam0", "cam1"}
    finally:
        store.close()


@pytest.mark.xfail(not HAVE_MODULES, reason="detect/track2d/recon not present yet", strict=False)
def test_preview_jpeg_only_encoded_while_a_client_is_attached(tmp_path):
    store = Store(tmp_path / "p.db")
    pl = Pipeline(_file_cfg(), store, tmp_path, save_clips=False)
    pl.start()
    try:
        assert _wait(lambda: pl._cam_t.get("cam0", 0) > 0.3, 30)
        assert pl.latest_jpeg("cam0") is None                  # nobody is watching
        pl.preview_client_add("cam0")
        got = _wait(lambda: pl.latest_jpeg("cam0") is not None or pl.is_finished(), 30)
        jpg = pl.latest_jpeg("cam0")
        pl.preview_client_remove("cam0")
        if jpg is None and pl.is_finished():
            pytest.skip("fixture ended before the client attached")
        assert got and jpg[:2] == b"\xff\xd8"
        assert pl.latest_jpeg("cam0") is None                  # no stale frame kept
    finally:
        pl.stop()
        store.close()


@pytest.mark.xfail(not HAVE_MODULES, reason="detect/track2d/recon not present yet", strict=False)
def test_clip_ring_frames_survive_buffer_recycling(tmp_path):
    """Clips are written from a ring whose buffers are recycled: they must contain frames."""
    import cv2
    store = Store(tmp_path / "p.db")
    pl = Pipeline(_file_cfg(), store, tmp_path, save_clips=True)
    sid = store.create_session("clips")
    pl.set_session(sid)
    pl.start()
    try:
        assert _wait(pl.is_finished, 90)
    finally:
        pl.stop()
    try:
        with_clip = [s for s in store.list_shots(sid) if s.clip_path]
        assert with_clip
        cap = cv2.VideoCapture(with_clip[0].clip_path)
        ok, img = cap.read()
        cap.release()
        assert ok and img.shape[1] == 480 and img.mean() > 5
    finally:
        store.close()


# ------------------------------------------------------------- RTMP source targets
def test_bare_rtmp_stream_name_resolves_to_local_url(tmp_path):
    from hiveshot.rtmp_server import RtmpServer
    rtmp = RtmpServer(data_dir=tmp_path)
    mk = lambda target: cfgmod.SourceConfig(cam_id="c", kind="rtmp", target=target)  # noqa: E731
    assert pipemod._spec_from(mk("cam0"), tmp_path, rtmp).target == "rtmp://127.0.0.1:1935/cam0"
    assert pipemod._spec_from(mk(" cam1/ "), tmp_path, rtmp).target == rtmp.url_for("cam1")
    full = "rtmp://192.168.1.5:1935/live/x"
    assert pipemod._spec_from(mk(full), tmp_path, rtmp).target == full       # URLs untouched
    assert pipemod._spec_from(mk("cam0"), tmp_path).target == "rtmp://127.0.0.1:1935/cam0"
    other = cfgmod.SourceConfig(cam_id="u", kind="url", target="cam0")
    assert pipemod._spec_from(other, tmp_path, rtmp).target == "cam0"        # only rtmp kind


# ------------------------------------------------------------ status warnings
def test_status_warnings_and_calibration_loaded(tmp_path):
    cfg = cfgmod.AppConfig(calibration_path=str(tmp_path / "missing.json"), sources=[
        cfgmod.SourceConfig(cam_id="a", kind="rtmp", target="a"),
        cfgmod.SourceConfig(cam_id="b", kind="rtmp", target="b")])
    pl = Pipeline(cfg, Store(tmp_path / "w.db"), tmp_path, save_clips=False)
    st = pl.status()
    assert st["calibration_loaded"] is False
    assert "no calibration loaded: 3D reconstruction disabled" in st["warnings"]
    pl._frame_size = {"a": (1280, 720)}
    pl._calib = ({"a": CameraIntrinsics("a", 1920, 1080, 1000, 1000, 960, 540, (0, 0, 0, 0, 0), 0.1)},
                 {})
    assert any("camera a resolution mismatch" in w for w in pl.status()["warnings"])
    pl.store.close()

    single = Pipeline(cfgmod.AppConfig(sources=[cfgmod.SourceConfig(
        cam_id="a", kind="file", target="x.mp4")]), Store(tmp_path / "s.db"), tmp_path)
    assert "single-camera" in " ".join(single.status()["warnings"])
    single.store.close()

    ok = Pipeline(_file_cfg(), Store(tmp_path / "o.db"), tmp_path)
    assert ok.status()["calibration_loaded"] is True and ok.status()["warnings"] == []
    ok.store.close()

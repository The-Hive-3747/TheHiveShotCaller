import itertools
import os
import socket
import sys
import time

import cv2
import numpy as np
import pytest

from hiveshot.ingest import (
    CaptureThread,
    MultiCapture,
    SourceSpec,
    VideoSource,
    list_devices,
)
from hiveshot.models import SourceKind
from hiveshot.rtmp_server import RtmpServer, RtmpServerError

N = 30


def make_video(path, n=N):
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (320, 240))
    assert w.isOpened()
    for i in range(n):
        img = np.zeros((240, 320, 3), np.uint8)
        img[:, : 10 * (i + 1)] = 255
        w.write(img)
    w.release()
    return path


@pytest.fixture
def vid(tmp_path):
    return make_video(tmp_path / "a.mp4")


def spec(vid, cam="c0", loop=False):
    return SourceSpec(cam, SourceKind.FILE, str(vid), loop=loop)


def test_reads_exactly_n_then_none(vid):
    s = VideoSource(spec(vid))
    frames = []
    while True:
        f = s.read()
        if f is None:
            break
        frames.append(f)
    assert len(frames) == N
    assert [f.frame_idx for f in frames] == list(range(N))
    assert frames[0].image.shape == (240, 320, 3)
    assert s.read() is None
    ts = [f.t_source for f in frames]
    assert all(t is not None for t in ts)
    assert all(b > a for a, b in itertools.pairwise(ts))
    assert s.props()["width"] == 320
    s.close()


def test_frames_distinguishable(vid):
    s = VideoSource(spec(vid))
    widths = []
    for _ in range(N):
        f = s.read()
        widths.append(int((f.image[120, :, 0] > 128).sum()))
    s.close()
    assert widths == sorted(widths) and len(set(widths)) > N // 2


def test_loop_monotonic(vid):
    s = VideoSource(spec(vid, loop=True))
    fs = [s.read() for _ in range(N * 2 + 5)]
    s.close()
    assert all(f is not None for f in fs)
    assert [f.frame_idx for f in fs] == list(range(N * 2 + 5))
    ts = [f.t_source for f in fs]
    assert all(b > a for a, b in itertools.pairwise(ts))


def test_missing_file_raises(tmp_path):
    with pytest.raises(IOError):
        VideoSource(spec(tmp_path / "nope.mp4"))


@pytest.mark.timing
def test_slow_consumer_drops_oldest(vid):
    ct = CaptureThread(spec(vid), maxsize=4).start()
    deadline = time.time() + 5
    while ct.stats()["frames_read"] < N and time.time() < deadline:
        time.sleep(0.01)
    st = ct.stats()
    assert st["frames_read"] == N
    assert st["dropped"] == N - 4
    assert st["fps"] > 0
    first = ct.get(1.0)
    assert first.frame_idx == N - 4  # oldest were dropped
    assert ct.latest().frame_idx == N - 1
    t0 = time.time()
    ct.stop()
    # F14: generous bound so a loaded machine does not flake; still proves
    # stop() returns promptly rather than hanging.
    assert time.time() - t0 < 5
    assert not ct.stats()["is_alive"]


@pytest.mark.timing
def test_multicapture(tmp_path):
    a = make_video(tmp_path / "a.mp4")
    b = make_video(tmp_path / "b.mp4")
    mc = MultiCapture([spec(a, "left", loop=True), spec(b, "right", loop=True)]).start()
    try:
        deadline = time.time() + 5
        while len(mc.latest_all()) < 2 and time.time() < deadline:
            time.sleep(0.02)
        assert set(mc.latest_all()) == {"left", "right"}
        time.sleep(0.2)
        st = mc.stats_all()
        assert st["left"]["fps"] > 0 and st["right"]["fps"] > 0
    finally:
        t0 = time.time()
        mc.stop_all()
        assert time.time() - t0 < 5  # F14: tolerant of a loaded machine


def _run_with_fake_sleep(monkeypatch, cap_cls, n_sleeps):
    """Run a device CaptureThread whose backoff sleeps are recorded, not
    waited; the n_sleeps-th sleep requests stop. No wall-clock dependence."""
    monkeypatch.setattr(cv2, "VideoCapture", cap_cls)
    ct = CaptureThread(SourceSpec("bad", SourceKind.DEVICE, 99))
    slept: list[float] = []

    def fake_sleep(seconds):
        slept.append(seconds)
        if len(slept) >= n_sleeps:
            ct._stop.set()
            return True
        return False

    ct._sleep = fake_sleep
    ct.start()
    ct._thread.join(10)  # generous hang guard only; completion is event-driven
    assert not ct._thread.is_alive()
    return ct, slept


def test_device_reconnect_backoff_reports_error(monkeypatch):
    # Open always fails: backoff doubles 0.5 -> 5 s then stays capped, and
    # last_error is set (deterministic: fake sleep, no timing assertions).
    class NoOpen(_StubCap):
        def isOpened(self):
            return False

    ct, slept = _run_with_fake_sleep(monkeypatch, NoOpen, 6)
    assert slept == [0.5, 1.0, 2.0, 4.0, 5.0, 5.0]
    st = ct.stats()
    assert st["last_error"] and "cannot open" in st["last_error"]
    assert st["reconnects"] == 0 and st["frames_read"] == 0
    assert not st["is_alive"]


def test_device_stream_lost_counts_reconnects(monkeypatch):
    # Opens fine but never delivers frames: each re-open is a counted
    # reconnect, backoff keeps growing (no frames -> no reset), error says so.
    class NoFrames(_StubCap):
        def read(self):
            return False, None

    ct, slept = _run_with_fake_sleep(monkeypatch, NoFrames, 5)
    assert slept == [0.5, 1.0, 2.0, 4.0, 5.0]
    st = ct.stats()
    assert st["reconnects"] == 4  # 5 opens, first is not a reconnect
    assert st["last_error"] == "no frames received"
    assert not st["is_alive"]


def test_rtmp_missing_binary(tmp_path):
    srv = RtmpServer(binary=tmp_path / "bin" / "mediamtx.exe", data_dir=tmp_path)
    assert srv.is_available() is False
    with pytest.raises(RtmpServerError, match="mediamtx.exe"):
        srv.start()
    assert srv.url_for("cam1") == "rtmp://127.0.0.1:1935/cam1"
    srv.stop()  # safe when never started


def test_rtmp_default_binary_name():
    assert RtmpServer(binary=None).binary.name == "mediamtx.exe"


def test_rtmp_config_written(tmp_path):
    srv = RtmpServer(binary=tmp_path / "x.exe", data_dir=tmp_path / "data")
    p = srv.write_config()
    text = p.read_text()
    assert p.name == "mediamtx.yml"
    assert "rtmp: yes" in text and ":1935" in text
    for proto in ("rtsp", "webrtc", "hls", "srt"):
        assert f"{proto}: no" in text


@pytest.mark.timing
def test_list_devices_returns_list():
    t0 = time.time()
    res = list_devices()
    assert isinstance(res, list)
    assert time.time() - t0 < 15


live = pytest.mark.skipif(os.environ.get("HIVESHOT_LIVE") != "1",
                          reason="set HIVESHOT_LIVE=1")


@pytest.mark.live
@live
def test_live_webcam_reads():
    ct = CaptureThread(SourceSpec("cam", SourceKind.DEVICE, 0)).start()
    time.sleep(3)
    st = ct.stats()
    ct.stop()
    assert st["frames_read"] > 0


@pytest.mark.live
@live
def test_live_rtmp_server_start_stop(tmp_path):
    port = int(os.environ.get("HIVESHOT_RTMP_PORT", "1935"))
    srv = RtmpServer(data_dir=tmp_path, port=port)
    if not srv.is_available():
        pytest.skip("bin/mediamtx.exe not present")
    srv.start()
    proc = srv._proc
    try:
        listening = False
        deadline = time.time() + 5
        while time.time() < deadline and proc.poll() is None:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                    listening = True
                    break
            except OSError:
                time.sleep(0.1)
        assert proc.poll() is None, "mediamtx exited early"
        assert listening, f"port {port} not listening within 5 s"
    finally:
        srv.stop()
    assert proc.poll() is not None
    assert not srv.is_running()


@pytest.mark.timing
def test_realtime_pacing(vid):
    sp = SourceSpec("rt", SourceKind.FILE, str(vid), realtime=True)
    ct = CaptureThread(sp, maxsize=64)
    t0 = time.perf_counter()
    ct.start()
    got = 0
    while ct.get(3.0) is not None:
        got += 1
        if got == N:
            break
    elapsed = time.perf_counter() - t0
    st = ct.stats()
    ct.stop()
    assert got == N
    # F14: pacing is proven by a lower bound (30 frames at 30 fps cannot
    # arrive in under ~0.8 s unless pacing is broken); the upper bound is only
    # a hang guard, loose for loaded machines. The fps band is wide for the
    # same reason.
    assert elapsed >= 0.8
    assert elapsed <= 10.0
    assert 15 <= st["fps"] <= 45


def test_realtime_missing_file_sets_finished(tmp_path):
    # F5: a realtime FILE that cannot open must end the pipeline (finished).
    sp = SourceSpec("rt", SourceKind.FILE, str(tmp_path / "nope.mp4"), realtime=True)
    ct = CaptureThread(sp).start()
    deadline = time.time() + 2
    while time.time() < deadline:
        st = ct.stats()
        if st["finished"] and not st["is_alive"]:
            break
        time.sleep(0.02)
    st = ct.stats()
    ct.stop()
    assert st["finished"] is True
    assert st["is_alive"] is False
    assert st["last_error"]
    assert ct.get(0.1) is None


def test_file_eof_sets_finished(vid):
    ct = CaptureThread(spec(vid), maxsize=64).start()
    deadline = time.time() + 5
    while not ct.stats()["finished"] and time.time() < deadline:
        time.sleep(0.02)
    assert ct.stats()["finished"] is True
    ct.stop()


class _StubCap:
    """Fake cv2.VideoCapture: reports 1000 fps, synthetic frames ~100/s."""

    def __init__(self, *a, **k):
        self.n = 0
        self.fps = 1000.0

    def isOpened(self):
        return True

    def release(self):
        pass

    def set(self, *a):
        return True

    def get(self, prop):
        if prop == cv2.CAP_PROP_FPS:
            return self.fps
        if prop == cv2.CAP_PROP_FRAME_WIDTH:
            return 64
        if prop == cv2.CAP_PROP_FRAME_HEIGHT:
            return 48
        if prop == cv2.CAP_PROP_POS_MSEC:
            return self.n * 10.0
        return 0.0

    def read(self):
        time.sleep(0.01)
        self.n += 1
        return True, np.zeros((48, 64, 3), np.uint8)


@pytest.mark.timing
@pytest.mark.parametrize("bad", [1000.0, 0.0, -5.0, float("nan")])
def test_props_fps_sanity_fallback(monkeypatch, bad):
    # F11b: insane reported fps -> hint/30 first, measured later; raw exposed.
    class Cap(_StubCap):
        def __init__(self, *a, **k):
            super().__init__()
            self.fps = bad

    monkeypatch.setattr(cv2, "VideoCapture", Cap)
    monkeypatch.setattr("hiveshot.ingest._FPS_MEASURE_AFTER_S", 0.3)
    s = VideoSource(SourceSpec("d", SourceKind.DEVICE, 0))
    p0 = s.props()
    assert p0["fps"] == 30.0
    assert (p0["fps_reported"] == bad) or (bad != bad and p0["fps_reported"] != p0["fps_reported"])
    s2 = VideoSource(SourceSpec("d", SourceKind.DEVICE, 0, fps_hint=25.0))
    assert s2.props()["fps"] == 25.0
    s2.close()
    t0 = time.time()
    while time.time() - t0 < 0.5:
        s.read()
    p1 = s.props()
    s.close()
    assert p1["fps"] != 30.0 and 0 < p1["fps"] <= 240
    assert 30 <= p1["fps"] <= 110  # ~100 fps stub, loose for loaded machines


def test_sane_fps_passthrough(monkeypatch):
    class Cap(_StubCap):
        def __init__(self, *a, **k):
            super().__init__()
            self.fps = 60.0

    monkeypatch.setattr(cv2, "VideoCapture", Cap)
    s = VideoSource(SourceSpec("d", SourceKind.DEVICE, 0))
    assert s.props()["fps"] == 60.0 and s.props()["fps_reported"] == 60.0
    s.close()


def test_device_t_source_from_pos_msec(monkeypatch):
    # F11a: backend POS_MSEC exposed as t_source; t_capture stays read time.
    monkeypatch.setattr(cv2, "VideoCapture", _StubCap)
    s = VideoSource(SourceSpec("d", SourceKind.DEVICE, 0))
    fs = [s.read() for _ in range(5)]
    s.close()
    ts = [f.t_source for f in fs]
    assert ts == pytest.approx([0.01, 0.02, 0.03, 0.04, 0.05])
    assert all(b > a for a, b in itertools.pairwise(f.t_capture for f in fs))


def test_device_t_source_none_when_zero(monkeypatch):
    class Cap(_StubCap):
        def get(self, prop):
            return 0.0 if prop == cv2.CAP_PROP_POS_MSEC else super().get(prop)

    monkeypatch.setattr(cv2, "VideoCapture", Cap)
    s = VideoSource(SourceSpec("d", SourceKind.DEVICE, 0))
    assert s.read().t_source is None
    s.close()


@pytest.mark.timing
def test_latency_estimate_stats(monkeypatch):
    # F11a: diagnostic-only; buffered bursts (late arrivals vs nominal fps).
    class Cap(_StubCap):
        def __init__(self, *a, **k):
            super().__init__()
            self.fps = 100.0

        def read(self):
            time.sleep(0.03)  # 33 fps actual vs 100 nominal -> ~0.02 s excess
            self.n += 1
            return True, np.zeros((48, 64, 3), np.uint8)

    monkeypatch.setattr(cv2, "VideoCapture", Cap)
    ct = CaptureThread(SourceSpec("d", SourceKind.DEVICE, 0)).start()
    deadline = time.time() + 5
    while ct.stats()["frames_read"] < 10 and time.time() < deadline:
        time.sleep(0.02)
    st = ct.stats()
    ct.stop()
    assert st["latency_estimate_s"] > 0.005
    assert st["props"]["fps"] == 100.0


@pytest.mark.timing
def test_list_devices_cold_first_index_and_cache(monkeypatch):
    # Index 0 is slow (cold MSMF init, 1.5 s) -> must not be dropped by the
    # 1 s default; second call is served from the 30 s cache.
    import hiveshot.ingest as ing
    calls = []

    def slow_probe(index, out):
        calls.append(index)
        if index == 0:
            time.sleep(1.5)
            out["info"] = {"index": 0, "width": 1, "height": 1, "fps": 30.0,
                           "read_ok": True}

    monkeypatch.setattr(ing, "_probe_one", slow_probe)
    monkeypatch.setattr(ing, "_device_cache", None)
    r1 = ing.list_devices(max_index=2)
    assert [d["index"] for d in r1] == [0]
    n = len(calls)
    t0 = time.perf_counter()
    r2 = ing.list_devices(max_index=2)
    assert time.perf_counter() - t0 < 0.5
    assert r2 == r1 and len(calls) == n
    assert ing.list_devices(max_index=2, use_cache=False) == r1
    assert len(calls) > n
    monkeypatch.setattr(ing, "_device_cache", None)  # do not leak fake result


def test_list_devices_empty_not_cached(monkeypatch):
    import hiveshot.ingest as ing
    monkeypatch.setattr(ing, "_probe_one", lambda i, out: None)
    monkeypatch.setattr(ing, "_device_cache", None)
    assert ing.list_devices(max_index=1) == []
    assert ing._device_cache is None


def _busy_socket():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(16)  # never accepted; deep backlog so repeat probes connect
    return s, s.getsockname()[1]


def test_rtmp_port_busy_other_process(tmp_path, monkeypatch):
    binary = tmp_path / "mediamtx.exe"
    binary.write_bytes(b"x")
    busy, port = _busy_socket()
    try:
        srv = RtmpServer(binary=binary, data_dir=tmp_path, port=port)
        monkeypatch.setattr(srv, "_mediamtx_pids", lambda: [])
        with pytest.raises(RtmpServerError, match="busy by another process"):
            srv.start()
        assert not srv.is_running() and srv._proc is None
    finally:
        busy.close()


def test_rtmp_adopts_orphan_and_stop_does_not_kill(tmp_path, monkeypatch):
    import subprocess as sp
    binary = tmp_path / "mediamtx.exe"
    binary.write_bytes(b"x")
    busy, port = _busy_socket()
    killed = []
    monkeypatch.setattr(sp, "run", lambda cmd, **k: killed.append(cmd))
    try:
        srv = RtmpServer(binary=binary, data_dir=tmp_path, port=port)
        monkeypatch.setattr(srv, "_mediamtx_pids", lambda: [4242])
        srv.start()
        assert srv.adopted and srv.is_running() and srv._proc is None
        srv.stop()
        assert killed == [] and not srv.adopted
    finally:
        busy.close()


def test_rtmp_adopted_killed_only_with_kill_adopted(tmp_path, monkeypatch):
    import subprocess as sp
    binary = tmp_path / "mediamtx.exe"
    binary.write_bytes(b"x")
    busy, port = _busy_socket()
    killed = []
    monkeypatch.setattr(sp, "run", lambda cmd, **k: killed.append(cmd))
    try:
        srv = RtmpServer(binary=binary, data_dir=tmp_path, port=port,
                         kill_adopted=True)
        monkeypatch.setattr(srv, "_mediamtx_pids", lambda: [4242])
        srv.start()
        srv.stop()
        assert len(killed) == 1 and "4242" in killed[0]
    finally:
        busy.close()


def test_rtmp_mediamtx_pids_parses_tasklist(tmp_path, monkeypatch):
    import subprocess as sp
    srv = RtmpServer(binary=tmp_path / "x.exe", data_dir=tmp_path)
    out = '"mediamtx.exe","1234","Console","1","20,000 K"' + chr(10)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sp, "run", lambda *a, **k: sp.CompletedProcess(a, 0, out, ""))
    assert srv._mediamtx_pids() == [1234]
    out2 = "INFO: No tasks are running which match the specified criteria." + chr(10)
    monkeypatch.setattr(sp, "run", lambda *a, **k: sp.CompletedProcess(a, 0, out2, ""))
    assert srv._mediamtx_pids() == []

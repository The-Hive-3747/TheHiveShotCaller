"""Loose per-frame processing-time bound (single thread). The real figure is printed (run
with -s, or see the captured output on failure); the bound is loose so a loaded machine does
not flake. Measured stage numbers live in evidence/m5_perf/stage_timing.md.

`test_realtime_no_drops` is the whole-pipeline realtime check; it only runs with
HIVESHOT_PERF=1 because the result depends on the machine."""

import json
import os
import time
from pathlib import Path

import cv2
import pytest

from hiveshot import config as cfgmod
from hiveshot.detect import DetectorConfig
from hiveshot.pipeline import Pipeline, ScaledDetector
from hiveshot.store import Store
from hiveshot.track2d import Tracker2D

FIX = Path(__file__).resolve().parent.parent / "fixtures" / "synth_basic" / "cam0.mp4"
N_FRAMES = 60
BOUND_MS = 15.0


def test_detector_plus_tracker_mean_frame_time_under_bound():
    cap = cv2.VideoCapture(str(FIX))
    frames = []
    while len(frames) < N_FRAMES:
        ok, img = cap.read()
        if not ok:
            break
        frames.append(img)
    cap.release()
    assert len(frames) == N_FRAMES, "fixture too short"
    dsec = cfgmod.AppConfig().detector
    det = ScaledDetector(DetectorConfig.from_dict(dsec.model_dump()), dsec.motion_scale)
    trk = Tracker2D("cam0")
    old_threads = cv2.getNumThreads()
    cv2.setNumThreads(1)                                   # single thread
    try:
        # throw-away call on a separate detector so first-use code paths are loaded; the
        # measured detector's own background-model warm-up is part of the real cost
        ScaledDetector(DetectorConfig()).detect(frames[0], 0, 0.0, "w")
        per_frame = []
        n_dets = 0
        for i, img in enumerate(frames):
            t0 = time.perf_counter()
            small = det.shrink(img)
            dets = det.detect(small, i, i / 60.0, "cam0")
            trk.update(dets, i, i / 60.0)
            trk.closed()
            per_frame.append((time.perf_counter() - t0) * 1000.0)
            n_dets += len(dets)
    finally:
        cv2.setNumThreads(old_threads)
    mean = sum(per_frame) / len(per_frame)
    median = sorted(per_frame)[len(per_frame) // 2]
    print(f"\nper-frame detector+tracker time over {N_FRAMES} frames at "
          f"{frames[0].shape[1]}x{frames[0].shape[0]}: mean {mean:.2f} ms, "
          f"median {median:.2f} ms, max {max(per_frame):.2f} ms "
          f"(bound {BOUND_MS} ms, {n_dets} detections)")
    assert n_dets > 0, "detector found nothing: the timing would be meaningless"
    assert mean < BOUND_MS, f"mean {mean:.2f} ms >= {BOUND_MS} ms"


@pytest.mark.perf
@pytest.mark.skipif(os.environ.get("HIVESHOT_PERF") != "1",
                    reason="realtime throughput depends on the machine; set HIVESHOT_PERF=1")
def test_realtime_no_drops(tmp_path):
    r"""The whole pipeline (capture, detection, tracking, reconstruction, shot fitting, clip
    writing) keeps up with a 720p60 two-camera stream played in real time: no frame is
    dropped by either camera and every shot is classified as in the truth file.

    Manual command (idle machine, nothing else running):
        $env:HIVESHOT_PERF = "1"; .venv\Scripts\python.exe -m pytest tests/test_perf.py -k realtime -s
    """
    fx = Path(__file__).resolve().parent.parent / "fixtures" / "synth_20"
    cfg = cfgmod.AppConfig(sources=[
        cfgmod.SourceConfig(cam_id=f"cam{i}", kind="file", target=str(fx / f"cam{i}.mp4"),
                            realtime=True, loop=False) for i in (0, 1)])
    store = Store(tmp_path / "p.db")
    pl = Pipeline(cfg, store, tmp_path, save_clips=True)
    sid = store.create_session("perf")
    pl.set_session(sid)
    pl.start()
    try:
        deadline = time.time() + 90
        while time.time() < deadline and not pl.is_finished():
            time.sleep(0.2)
        assert pl.is_finished(), "pipeline did not finish the 17 s fixture within 90 s"
        st = pl.status()
    finally:
        pl.stop()
    cams = {c: (v["frames_read"], v["dropped"]) for c, v in st["cameras"].items()}
    print(f"\nrealtime synth_20: frames/dropped per camera {cams}; timing {st['timing']}")
    assert all(read > 900 for read, _ in cams.values())
    assert all(dropped == 0 for _, dropped in cams.values()), cams
    truth = sorted(json.loads((fx / "shots.json").read_text()), key=lambda t: t["t_launch"])
    shots = sorted(store.list_shots(sid), key=lambda s: s.t_launch)
    store.close()
    assert [s.result.value == "made" for s in shots] == [bool(t["made"]) for t in truth]

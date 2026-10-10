"""Loose per-frame processing-time bound (single thread). The real figure is printed (run
with -s, or see the captured output on failure); the bound is loose so a loaded machine does
not flake. Measured stage numbers live in evidence/m5_perf/stage_timing.md."""

import time
from pathlib import Path

import cv2

from hiveshot import config as cfgmod
from hiveshot.detect import DetectorConfig
from hiveshot.pipeline import ScaledDetector
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

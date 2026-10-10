"""Detector tests. Expected results come from the synthetic fixture's truth JSON.

The synthetic ball is solid BGR (0,200,255) (HSV hue ~23, S/V 255), which falls
inside the default POLLEN range, so the fixture test runs with color enabled.
"""

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from hiveshot.detect import BallDetector, DetectorConfig
from hiveshot.models import BallType

FIXROOT = Path(__file__).resolve().parent.parent / "fixtures"
FIXTURES = ["synth_basic", "synth_burst", "synth_20", "synth_240"]
W, H = 1920, 1080


def _run(cfg: DetectorConfig, fixture: str = "synth_basic"):
    fix = FIXROOT / fixture
    truth = json.loads((fix / "cam0_truth.json").read_text())
    det = BallDetector(cfg)
    cap = cv2.VideoCapture(str(fix / "cam0.mp4"))
    out = []
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        out.append(det.detect(frame, i, i / truth["fps"], "cam0"))
        i += 1
    cap.release()
    assert i == truth["n_frames"]
    return truth, out


def _score(truth, dets_per_frame):
    """Truth balls count only while their center is inside the image."""
    tp = fp = n_truth = 0
    for fr, dets in zip(truth["frames"], dets_per_frame, strict=True):
        vis = [b for b in fr["balls"] if 0 <= b["u"] < W and 0 <= b["v"] < H]
        n_truth += len(vis)
        used = set()
        for d in dets:
            hit = None
            for k, b in enumerate(vis):
                if (k not in used and np.hypot(d.u - b["u"], d.v - b["v"]) <= 6
                        and abs(d.radius_px - b["radius_px"]) <= 0.5 * b["radius_px"]):
                    hit = k
                    break
            if hit is None:
                fp += 1
            else:
                used.add(hit)
                tp += 1
    return tp, fp, n_truth


@pytest.fixture(scope="module")
def color_run():
    return _run(DetectorConfig(use_color=True))


@pytest.mark.parametrize("fixture", FIXTURES)
def test_fixture_recall_precision_color(fixture):
    truth, dets = _run(DetectorConfig(use_color=True), fixture)
    tp, fp, n = _score(truth, dets)
    assert n > 100
    assert n == sum(len(f['balls']) for f in truth['frames'])  # all truth in frame
    assert tp / n >= 0.95
    assert tp / max(1, tp + fp) >= 0.95


@pytest.mark.parametrize("fixture", FIXTURES)
def test_fixture_recall_precision_motion_only(fixture):
    truth, dets = _run(DetectorConfig(use_color=False), fixture)
    tp, fp, n = _score(truth, dets)
    assert tp / n >= 0.95
    assert tp / max(1, tp + fp) >= 0.95
    assert all(d.ball_type == BallType.UNKNOWN for fr in dets for d in fr)


def test_fixture_ball_type_pollen(color_run):
    _, dets = color_run
    types = [d.ball_type for fr in dets for d in fr]
    assert types and all(t == BallType.POLLEN for t in types)


def test_detection_fields(color_run):
    _, dets = color_run
    d = next(fr[0] for fr in dets if fr)
    assert d.cam_id == "cam0" and 0 < d.confidence <= 1.0
    assert 0 <= d.u < W and 0 <= d.v < H


def _scene(color_bgr, pos, r=20, size=(540, 960)):
    img = np.full((*size, 3), 40, np.uint8)
    cv2.circle(img, pos, r, color_bgr, -1, cv2.LINE_AA)
    return img


def test_nectar_classified_and_scaled_coordinates():
    det = BallDetector(DetectorConfig(process_scale=0.5))
    bg = np.full((540, 960, 3), 40, np.uint8)
    for i in range(10):
        det.detect(bg, i, i / 60, "c")
    magenta = (200, 40, 200)  # BGR purple/magenta
    out = det.detect(_scene(magenta, (480, 270)), 10, 10 / 60, "c")
    assert len(out) == 1
    assert out[0].ball_type == BallType.NECTAR
    assert abs(out[0].u - 480) < 3 and abs(out[0].v - 270) < 3
    assert 15 < out[0].radius_px < 26


def test_static_scene_has_no_detections_and_reset():
    det = BallDetector()
    bg = np.full((540, 960, 3), 40, np.uint8)
    assert all(det.detect(bg, i, i / 60, "c") == [] for i in range(20))
    det.reset()
    assert det.detect(bg, 0, 0.0, "c") == []


def test_radius_filter_rejects_huge_blob():
    det = BallDetector()
    bg = np.full((540, 960, 3), 40, np.uint8)
    for i in range(10):
        det.detect(bg, i, 0, "c")
    huge = _scene((0, 200, 255), (400, 270), r=120)
    assert det.detect(huge, 10, 0, "c") == []


def test_draw_returns_annotated_copy(color_run):
    frame = np.zeros((H, W, 3), np.uint8)
    _, dets = color_run
    ds = next(fr for fr in dets if fr)
    out = BallDetector.draw(frame, ds)
    assert out is not frame and out.shape == frame.shape
    assert frame.sum() == 0 and out.sum() > 0


def test_config_from_dict_ignores_unknown_keys():
    cfg = DetectorConfig.from_dict({"min_radius_px": 5, "pollen_hsv": [[1, 2, 3], [4, 5, 6]],
                                    "preview_fps": 15})
    assert cfg.min_radius_px == 5 and cfg.pollen_hsv == ((1, 2, 3), (4, 5, 6))

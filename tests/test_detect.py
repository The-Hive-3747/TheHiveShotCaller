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


@pytest.mark.parametrize("lr", [None, 0.001, 0, 0.0, -1])
@pytest.mark.parametrize("use_color", [True, False])
def test_bg_learning_rate_variants_detect(lr, use_color):
    det = BallDetector(DetectorConfig(bg_learning_rate=lr, use_color=use_color))
    bg = np.full((540, 960, 3), 40, np.uint8)
    for i in range(5):
        det.detect(bg, i, i / 60, "c")
    out = det.detect(_scene((0, 200, 255), (480, 270)), 5, 5 / 60, "c")
    assert len(out) == 1 and abs(out[0].u - 480) < 3


def test_bg_without_learning_rate_kwarg_is_supported():
    class NoLr:
        def apply(self, img):
            return np.full(img.shape[:2], 255, np.uint8)

    det = BallDetector(DetectorConfig(use_color=False))
    det._bg = NoLr()
    assert isinstance(det.detect(np.zeros((100, 100, 3), np.uint8), 0, 0.0, "c"), list)


# ---- gated (motion-bounding-box) colour path must equal the full-frame path -------------
class _FullFrameDetector(BallDetector):
    """Reference: the same motion & colour gating computed on the whole frame."""

    def _gated_masks(self, small, motion):
        cfg = self.cfg
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        pol = cv2.inRange(hsv, np.array(cfg.pollen_hsv[0], np.uint8),
                          np.array(cfg.pollen_hsv[1], np.uint8))
        nec = cv2.inRange(hsv, np.array(cfg.nectar_hsv[0], np.uint8),
                          np.array(cfg.nectar_hsv[1], np.uint8))
        m = cv2.bitwise_and(motion, cv2.bitwise_or(pol, nec))
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, self._kernel)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, self._kernel)
        return m, pol, nec


def _assert_same(a, b):
    assert len(a) == len(b)
    key = lambda d: (round(d.u, 3), round(d.v, 3))  # noqa: E731
    for x, y in zip(sorted(a, key=key), sorted(b, key=key), strict=True):
        assert abs(x.u - y.u) <= 0.01 and abs(x.v - y.v) <= 0.01
        assert abs(x.radius_px - y.radius_px) <= 0.01
        assert x.ball_type == y.ball_type


def _frames(fixture="synth_20", n=60):
    cap = cv2.VideoCapture(str(FIXROOT / fixture / "cam0.mp4"))
    for _ in range(n):
        ok, f = cap.read()
        if not ok:
            break
        yield f
    cap.release()


@pytest.mark.parametrize("scale", [0.5, 0.37, 1.0])
def test_gated_path_identical_to_full_frame_on_synth_20(scale):
    cfg = DetectorConfig(process_scale=scale)
    gated, full = BallDetector(cfg), _FullFrameDetector(cfg)
    total = 0
    for i, f in enumerate(_frames()):
        a = gated.detect(f, i, i / 60, "c")
        b = full.detect(f, i, i / 60, "c")
        _assert_same(a, b)
        total += len(a)
    assert total > 20  # the comparison is not vacuous


def _edge_scene(balls, size=(540, 960)):
    img = np.full((*size, 3), 40, np.uint8)
    for (x, y, r, col) in balls:
        cv2.circle(img, (x, y), r, col, -1, cv2.LINE_AA)
    return img


def test_gated_path_edge_cases_match_full_frame():
    yellow, magenta = (0, 200, 255), (200, 40, 200)
    cases = [
        [],                                                     # no motion
        [(480, 270, 20, yellow)],                               # interior
        [(15, 15, 20, yellow)],                                 # touching top-left corner
        [(945, 525, 20, magenta)],                              # touching bottom-right corner
        [(0, 270, 20, yellow), (959, 270, 20, magenta)],        # left and right edges
        [(100, 100, 20, yellow), (800, 450, 22, magenta)],      # disjoint motion regions
        [(300, 270, 20, yellow), (325, 270, 20, magenta)],      # overlapping
    ]
    for scale in (0.5, 0.33):
        for case in cases:
            gated = BallDetector(DetectorConfig(process_scale=scale))
            full = _FullFrameDetector(DetectorConfig(process_scale=scale))
            bg = _edge_scene([])
            for i in range(6):
                gated.detect(bg, i, 0, "c")
                full.detect(bg, i, 0, "c")
            img = _edge_scene(case)
            _assert_same(gated.detect(img, 6, 0, "c"), full.detect(img, 6, 0, "c"))


def test_color_only_mode_without_motion():
    det = BallDetector(DetectorConfig(use_motion=False))
    img = _edge_scene([(480, 270, 20, (0, 200, 255)), (200, 100, 18, (200, 40, 200))])
    out = det.detect(img, 0, 0, "c")
    assert sorted(d.ball_type.value for d in out) == ["nectar", "pollen"]
    assert det.detect(_edge_scene([]), 1, 0, "c") == []

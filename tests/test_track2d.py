"""Tracker tests. Fixture expectations are derived from the truth JSON.

The fixtures keep every ball in frame for its whole flight, so each shot must
yield exactly one closed track.
"""

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from hiveshot.detect import BallDetector, DetectorConfig
from hiveshot.models import BallType, Detection2D
from hiveshot.track2d import Tracker2D, Tracker2DConfig

FIXROOT = Path(__file__).resolve().parent.parent / "fixtures"
W, H = 1920, 1080


def _segments(truth):
    """ball -> list of [first, last] frame runs with center inside the image."""
    runs = {}
    for fr in truth["frames"]:
        for b in fr["balls"]:
            if 0 <= b["u"] < W and 0 <= b["v"] < H:
                segs = runs.setdefault(b["ball"], [])
                if segs and segs[-1][1] == fr["frame_idx"] - 1:
                    segs[-1][1] = fr["frame_idx"]
                else:
                    segs.append([fr["frame_idx"], fr["frame_idx"]])
    return runs


def _det(f, u, v, r=10.0, bt=BallType.POLLEN):
    return Detection2D("c", f, f / 60, u, v, r, bt, 1.0)


@pytest.mark.parametrize("fixture", ["synth_basic", "synth_burst"])
def test_fixture_tracks_match_truth_segments(fixture):
    FIX = FIXROOT / fixture
    truth = json.loads((FIX / "cam0_truth.json").read_text())
    shots = json.loads((FIX / "shots.json").read_text())
    segs = _segments(truth)
    assert len(segs) == len(shots) == 6
    assert all(len(v) == 1 for v in segs.values())  # continuous arcs, all in frame
    det = BallDetector(DetectorConfig())
    trk = Tracker2D("cam0")
    cap = cv2.VideoCapture(str(FIX / "cam0.mp4"))
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        trk.update(det.detect(frame, i, i / truth["fps"], "cam0"), i, i / truth["fps"])
        i += 1
    cap.release()
    tracks = trk.finish()
    assert len(tracks) == sum(len(s) for s in segs.values())
    assert trk.closed() == []  # already popped

    per_ball = {b: 0 for b in segs}
    for tr in tracks:
        owners = set()
        for d in tr.detections:
            near = min(truth["frames"][d.frame_idx]["balls"],
                       key=lambda b: np.hypot(d.u - b["u"], d.v - b["v"]))
            # nearest truth ball; split detections of touching balls can be off by ~10 px
            assert np.hypot(d.u - near["u"], d.v - near["v"]) <= 20
            hits = [near["ball"]]
            owners.add(hits[0])
        assert len(owners) == 1, "identity switch within a track"
        ball = owners.pop()
        per_ball[ball] += 1
        a, b = tr.detections[0].frame_idx, tr.detections[-1].frame_idx
        assert any(a <= s1 and b >= s0 for s0, s1 in segs[ball])
        assert tr.cam_id == "cam0" and len(tr.detections) >= 3
    assert all(per_ball[b] == len(segs[b]) for b in segs)
    assert all(v >= 1 for v in per_ball.values())  # every shot covered


def test_crossing_tracks_keep_identity():
    rng = np.random.default_rng(0)
    trk = Tracker2D("c")
    for f in range(21):
        a = (100 + 10 * f, 100 + 10 * f)       # ~14 px/frame, radius 10
        b = (400 - 20 * f, 100 + 10 * f)       # ~22 px/frame, radius 12; cross at f=10
        dets = [_det(f, *(np.array(a) + rng.normal(0, 0.5, 2)), r=10.0),
                _det(f, *(np.array(b) + rng.normal(0, 0.5, 2)), r=12.0)]
        trk.update(dets, f, f / 60)
    tracks = trk.finish()
    assert len(tracks) == 2
    for tr in tracks:
        assert len(tr.detections) == 21
        assert len({d.radius_px for d in tr.detections}) == 1


def test_track_survives_three_frame_dropout():
    trk = Tracker2D("c")
    dropped = {10, 11, 12}
    active = []
    for f in range(25):
        dets = [] if f in dropped else [_det(f, 50 + 15 * f, 80 + 6 * f)]
        active = trk.update(dets, f, f / 60)
    assert len(active) == 1
    tr = trk.finish()[0]
    frames = [d.frame_idx for d in tr.detections]
    assert frames == [f for f in range(25) if f not in dropped]
    assert {p[0] for p in tr.predicted} >= dropped
    assert tr.track_id == 0


def test_track_closes_after_max_missed_and_new_track_starts():
    trk = Tracker2D("c", Tracker2DConfig(max_missed=5))
    for f in range(6):
        trk.update([_det(f, 100 + 10 * f, 100)], f, f / 60)
    for f in range(6, 12):  # 6 consecutive misses > max_missed
        trk.update([], f, f / 60)
    closed = trk.closed()
    assert len(closed) == 1 and len(closed[0].detections) == 6
    assert trk.closed() == []
    for f in range(12, 16):
        trk.update([_det(f, 100 + 10 * f, 100)], f, f / 60)
    assert trk.finish()[0].track_id != closed[0].track_id


def test_min_hits_hides_short_tracks_and_noise():
    trk = Tracker2D("c")
    assert trk.update([_det(0, 10, 10)], 0, 0) == []
    assert trk.update([_det(1, 20, 10)], 1, 0) == []
    assert len(trk.update([_det(2, 30, 10)], 2, 0)) == 1
    trk2 = Tracker2D("c")
    trk2.update([_det(0, 10, 10)], 0, 0)
    trk2.update([], 1, 0)
    trk2.update([_det(2, 900, 900)], 2, 0)
    assert trk2.finish() == []


def test_ball_type_majority_vote():
    trk = Tracker2D("c")
    types = [BallType.POLLEN, BallType.NECTAR, BallType.NECTAR, BallType.UNKNOWN,
             BallType.NECTAR, BallType.POLLEN]
    for f, bt in enumerate(types):
        trk.update([_det(f, 10 * f, 50, bt=bt)], f, f / 60)
    assert trk.finish()[0].ball_type == BallType.NECTAR


def test_four_simultaneous_balls_parallel_tracks():
    trk = Tracker2D("c")
    for f in range(15):
        dets = [_det(f, 200 + 300 * k + 5 * f, 900 - 40 * f - 10 * k, r=10 + k)
                for k in range(4)]
        trk.update(dets, f, f / 60)
    tracks = trk.finish()
    assert len(tracks) == 4
    assert all(len({d.radius_px for d in t.detections}) == 1 for t in tracks)

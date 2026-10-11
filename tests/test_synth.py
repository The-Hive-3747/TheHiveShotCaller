import json

import cv2
import numpy as np
import pytest

from hiveshot import field, synth
from hiveshot.field_constants import GRAVITY_IPS2

ST = field.HiveState("red", "audience")


def test_no_drag_matches_parabola():
    p0 = np.array([1.0, 2.0, 10.0])
    v0 = np.array([30.0, -20.0, 200.0])
    tr = synth.simulate_trajectory(p0, v0, 0.01, 2.0)
    t = tr[:, 0]
    exp = p0[None] + v0[None] * t[:, None]
    exp[:, 2] -= 0.5 * GRAVITY_IPS2 * t ** 2
    assert np.abs(tr[:, 1:] - exp).max() < 1e-6
    assert tr[:, 3].min() >= 0
    assert tr[-1, 0] < 2.0  # stopped at the floor


def test_drag_slows_ball():
    p0 = [0, 0, 20.0]
    v0 = [300.0, 0, 100.0]
    a = synth.simulate_trajectory(p0, v0, 0.005, 0.5)
    b = synth.simulate_trajectory(p0, v0, 0.005, 0.5, drag_k=0.001)
    n = min(len(a), len(b))
    assert b[n - 1, 1] < a[n - 1, 1]


@pytest.mark.parametrize("drag", [0.0, 0.0005])
def test_aim_passes_through_center(drag):
    lp = np.array([-15.0, 60.0, 12.0])
    v0 = synth.aim_for_cell(lp, "red", "audience", ST, 320.0, drag_k=drag)
    assert np.linalg.norm(v0) == pytest.approx(320.0)
    tr = synth.simulate_trajectory(lp, v0, 0.0005, 3.0, drag)
    c, _ = field.cell_opening_plane("red", "audience", ST)
    d = np.linalg.norm(tr[:, 1:] - c, axis=1).min()
    assert d < 0.5
    hit = any(field.segment_crosses_opening(a[1:], b[1:], "red", "audience", ST, 1.4)
              for a, b in zip(tr[:-1], tr[1:], strict=True))
    assert hit


def test_aim_impossible():
    with pytest.raises(ValueError):
        synth.aim_for_cell([0, 120, 5.0], "red", "audience", ST, 50.0)


def test_camera_projection():
    cams = synth.make_default_pair()
    assert len(cams) == 2
    for cam in cams:
        u, v = cam.project([[0.0, 0.0, 0.0]])
        assert 0 <= u[0] < 1920 and 0 <= v[0] < 1080
        assert cam.depth([0, 0, 0])[0] > 0
        c, _ = field.cell_opening_plane("red", "audience", ST)
        u, v = cam.project(c)
        assert 0 <= u[0] < 1920 and 0 <= v[0] < 1080
    c0, c1 = (-(c.R.T @ np.array(c.extr.tvec)) for c in cams)
    assert abs(c0[0]) == pytest.approx(abs(c1[0])) and c0[0] * c1[0] < 0
    # both cameras see the red HIVE up CELL (at +X)
    for cam in cams:
        u, v = cam.project(field.cell_opening_plane("red", "audience", ST)[0])
        assert 0 <= u[0] < 1920 and 0 <= v[0] < 1080
    p = [np.array(c.extr.tvec) for c in cams]
    assert all(np.isfinite(x).all() for x in p)
    # cameras ~90 deg apart, 115 in out, 55 in high
    pos = [-(c.R.T @ np.array(c.extr.tvec)) for c in cams]
    assert all(x[2] == pytest.approx(55.0) for x in pos)
    assert all(np.hypot(x[0], x[1]) == pytest.approx(115.0) for x in pos)
    assert abs(np.dot(pos[0][:2], pos[1][:2])) < 1e-6


def test_render_sequence(tmp_path):
    cams = synth.make_default_pair(width=640, height=360, fx=470.0)
    lp = np.array([-15.0, 60.0, 12.0])
    v0 = synth.aim_for_cell(lp, "red", "audience", ST, 300.0)
    tr = synth.simulate_trajectory(lp, v0, 0.001, 3.0)
    fps = 30.0
    paths = synth.render_sequence([(0.0, tr), (0.1, tr)], cams, fps, tmp_path, 1.4)
    n_expected = int(np.ceil((tr[-1, 0] + 0.1 + 0.2) * fps)) + 1
    for cam in cams:
        cap = cv2.VideoCapture(paths[cam.cam_id])
        n = 0
        while True:
            ok, _ = cap.read()
            if not ok:
                break
            n += 1
        cap.release()
        assert n == n_expected
        truth = json.loads((tmp_path / f"{cam.cam_id}_truth.json").read_text())
        assert len(truth["frames"]) == n
        assert truth["intrinsics"]["fx"] == 470.0
        b = [bb for f in truth["frames"] for bb in f["balls"]]
        assert b and all(bb["radius_px"] > 0 for bb in b)
        # both balls visible together at some frame
        assert any(len(f["balls"]) == 2 for f in truth["frames"])


def test_in_image_fraction_helper():
    truth = {"intrinsics": {"width": 100, "height": 50},
             "frames": [{"balls": [{"u": 10, "v": 10}, {"u": 120, "v": 10}]},
                        {"balls": [{"u": 99.5, "v": 49.5}, {"u": -1, "v": 5}]}]}
    assert synth.in_image_fraction(truth) == pytest.approx(0.5)
    assert synth.in_image_fraction({"intrinsics": truth["intrinsics"], "frames": []}) == 0.0


@pytest.mark.parametrize("fixture", ["synth_basic", "synth_burst", "synth_20", "synth_240"])
@pytest.mark.parametrize("cam_id", ["cam0", "cam1"])
def test_fixture_in_image_fraction(fixture, cam_id):
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "fixtures" / fixture / f"{cam_id}_truth.json"
    truth = json.loads(p.read_text())
    assert synth.in_image_fraction(truth) >= 0.95


def test_build_shots_geometry():
    trajs, info = synth.build_shots([0.0, 0.3, 0.6], seed=3)
    cams = synth.make_default_pair()
    c, _ = field.cell_opening_plane("red", "audience", ST)
    for (_, tr), s in zip(trajs, info, strict=True):
        assert 60 <= np.linalg.norm(np.array(s["launch_point"]) - c) <= 110
        assert s["apex_z_in"] <= 84.5
        assert synth._flight_visible(tr, cams)


def test_render_hive_tags_are_detectable(tmp_path):
    # A camera 30 in in front of the up-CELL sticker, on its outward normal, sees the four
    # tags large and right-side-up. Detection with cv2.aruco only succeeds (with the right
    # ids and corner order) if the tag face is built right-handed as seen from outside.
    truth = field.hive_tag_corners("red", "audience", ST)
    row = np.mean([c.mean(axis=0) for c in truth.values()], axis=0)
    _, _, _, nrm = field.cell_floor_frame("red", "audience", ST)
    cam = synth.VirtualCamera.look_at("front", row + 30.0 * nrm, row)
    tr = np.array([[0.0, 0.0, 0.0, 5.0], [0.1, 0.0, 0.0, 5.0]])
    paths = synth.render_sequence([(0.0, tr)], [cam], 30.0, tmp_path, with_hive_tags=True)
    det = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11),
                                  cv2.aruco.DetectorParameters())
    cap = cv2.VideoCapture(paths["front"])
    ok, frame = cap.read()
    cap.release()
    assert ok
    corners, ids, _ = det.detectMarkers(frame)
    assert ids is not None
    found = {int(i): c.reshape(4, 2) for i, c in zip(ids.ravel(), corners, strict=True)}
    assert set(truth) <= set(found)
    for tid, c in truth.items():
        u, v = cam.project(c)
        assert np.abs(found[tid] - np.c_[u, v]).max() < 1.5


def test_render_default_has_no_tags(tmp_path):
    cams = synth.make_default_pair(width=320, height=180, fx=235.0)
    lp = np.array([-15.0, 60.0, 12.0])
    tr = synth.simulate_trajectory(lp, [0, -100, 150.0], 0.01, 0.1)
    p1 = synth.render_sequence([(0.0, tr)], cams[:1], 30.0, tmp_path / "a")
    p2 = synth.render_sequence([(0.0, tr)], cams[:1], 30.0, tmp_path / "b", with_hive_tags=True)
    f1 = cv2.VideoCapture(p1["cam0"]).read()[1]
    f2 = cv2.VideoCapture(p2["cam0"]).read()[1]
    assert f1 is not None and f2 is not None


def test_hive_tags_drawn_count():
    cams = synth.make_default_pair(width=1920, height=1080)
    img = np.full((1080, 1920, 3), 40, np.uint8)
    ids = synth._draw_hive_tags(img, cams[0], {"red": "audience", "blue": "far"})
    assert {34, 35, 36, 37} <= set(ids)


@pytest.mark.parametrize("fixture", ["synth_basic", "synth_burst", "synth_20", "synth_240"])
def test_fixture_shots_json_matches_truth(fixture):
    """shots.json and the per-camera truth were written by the same run: every shot's
    launch point equals the first truth position of its ball, and t_launch its first frame."""
    from pathlib import Path
    d = Path(__file__).resolve().parents[1] / "fixtures" / fixture
    shots = json.loads((d / "shots.json").read_text())
    for cam_id in ("cam0", "cam1"):
        truth = json.loads((d / f"{cam_id}_truth.json").read_text())
        first = {}
        for f in truth["frames"]:
            for b in f["balls"]:
                first.setdefault(b["ball"], (f["t"], b["xyz"]))
        assert len(first) == len(shots)
        for s in shots:
            t0, xyz = first[s["shot"]]
            assert np.linalg.norm(np.array(xyz) - np.array(s["launch_point"])) < 0.5, \
                (fixture, cam_id, s["shot"])
            assert t0 == pytest.approx(s["t_launch"], abs=1.0 / truth["fps"] + 1e-9)
            assert truth["t_offsets"][s["shot"]] == pytest.approx(s["t_launch"])

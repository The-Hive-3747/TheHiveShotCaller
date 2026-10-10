import math
from pathlib import Path

import cv2
import numpy as np
import pytest

from hiveshot import placement as pl
from hiveshot.synth import VirtualCamera

DOCS = Path(__file__).resolve().parent.parent / "docs"


def _cam(c, cam_id):
    return VirtualCamera(*pl.camera_from_pose(c["pos"], c["look_at"], c["hfov_deg"],
                                              1920, 1080, cam_id))


@pytest.mark.parametrize("option", ["gopro", "usb"])
def test_recommend_pair(option):
    rec = pl.recommend(option)
    sc = rec["pair_score"]
    assert 60.0 <= sc["mean_angle_deg"] <= 120.0
    assert sc["frac_in_both"] >= 0.90
    for k in ("A", "B", "C"):
        x, y, z = rec["cameras"][k]["pos"]
        assert max(abs(x), abs(y)) > 72.0          # outside the wall
        assert max(abs(x), abs(y)) <= 72.0 + 24.0  # but a reachable tripod spot
        assert 12.0 <= z <= 60.0                   # 60 in tripod
    # independent recomputation from the returned poses
    trajs = pl.sample_trajectories()
    again = pl.score_pair(_cam(rec["cameras"]["A"], "a"), _cam(rec["cameras"]["B"], "b"), trajs)
    assert again["frac_in_both"] == pytest.approx(sc["frac_in_both"])
    assert again["mean_angle_deg"] == pytest.approx(sc["mean_angle_deg"])


def test_camera_from_pose_centers_look_at_and_fov():
    look = (-12.0, 30.0, 55.0)
    intr, extr = pl.camera_from_pose((-78.0, 65.0, 40.0), look, 86.0, 1920, 1080, "t")
    cam = VirtualCamera(intr, extr)
    u, v = cam.project(look)
    assert math.hypot(u[0] - 960, v[0] - 540) < 2.0
    # horizontal FOV: tan(hfov/2) = (W/2)/fx
    assert math.degrees(2 * math.atan(960 / intr.fx)) == pytest.approx(86.0, abs=1e-6)


def test_candidates_outside_wall():
    c = pl.candidate_positions(78, (36, 58), range(0, 360, 30))
    assert len(c) == 24
    assert all(max(abs(x), abs(y)) >= 78 - 1e-9 for x, y, _ in c)
    with pytest.raises(ValueError):
        pl.candidate_positions(70, (36,), (0,))


def test_occlusion_detects_frame():
    # A ray running through the beam (x=-12.75, z=46 crosses it near y=1) is blocked;
    # the same point seen from beside the launch area is clear.
    pts = np.array([[-12.75, 10.0, 46.0]])
    assert pl.occluded((-12.75, -78.0, 46.0), pts)[0]
    assert not pl.occluded((-78.0, 65.0, 36.0), np.array([[-12.75, 60.0, 40.0]]))[0]


def test_map_files_exist_and_agree(tmp_path):
    svg, png = DOCS / "camera_placement.svg", DOCS / "camera_placement.png"
    assert svg.exists() and png.exists()
    text = svg.read_text(encoding="utf-8")
    for label in ("CAM A", "CAM B", "CAM C"):
        assert label in text
    rec = pl.recommend("gopro")
    for c in rec["cameras"].values():
        x, y, z = c["pos"]
        assert f"x={x:+.0f} y={y:+.0f}" in text and f"lens height {z:.0f} in" in text
    # regenerating gives the same SVG (map and recommend() cannot drift apart)
    pl.write_map("gopro", tmp_path / "m.svg", tmp_path / "m.png")
    assert (tmp_path / "m.svg").read_text(encoding="utf-8") == text
    img = cv2.imread(str(png))
    assert img.shape[:2] == (1600, 1600)


# ------------------------------------------------ calibration reference points (DoD 9)
@pytest.mark.parametrize("option", ["gopro", "usb"])
def test_all_reference_points_inside_both_images(option):
    from hiveshot import calib_targets

    rec = pl.recommend(option)
    w, h = pl.RESOLUTION
    margin = 20
    pts = calib_targets.field_reference_points()
    assert len(pts) == 8
    for k in ("A", "B"):
        cam = _cam(rec["cameras"][k], k)
        for name, p in pts:
            assert cam.depth(p)[0] > 1.0, (option, k, name)
            u, v = cam.project(p)
            assert margin <= u[0] <= w - margin and margin <= v[0] <= h - margin, (
                option, k, name, float(u[0]), float(v[0]))


@pytest.mark.parametrize("option", ["gopro", "usb"])
def test_extrinsics_from_reference_points_at_recommended_poses(option):
    """Click the 8 points (0.5 px noise) in both recommended cameras, solve, triangulate the
    up-CELL opening centre from hiveshot.field: < 2 px RMSE and < 1 in."""
    from hiveshot import calib, calib_targets, field

    rec = pl.recommend(option)
    pts = calib_targets.field_reference_points()
    xyz = np.array([p for _, p in pts])
    truth, _ = field.cell_opening_plane("red", "audience", field.HiveState("red", "audience"))
    for seed in range(5):
        rng = np.random.default_rng(seed)
        intr, ext, uv = {}, {}, {}
        for k in ("A", "B"):
            vc = _cam(rec["cameras"][k], k)
            u, v = vc.project(xyz)
            clicks = np.c_[u, v] + rng.normal(0, 0.5, (8, 2))
            intr[k] = vc.intr
            ext[k] = calib.solve_extrinsics_from_points(vc.intr, clicks, xyz, k)
            rep = calib.reprojection_report(vc.intr, ext[k], clicks, xyz)
            assert rep["rmse_px"] < 2.0
            cu, cv = vc.project(truth)
            uv[k] = np.array([cu[0], cv[0]]) + rng.normal(0, 0.5, 2)
        est, res = calib.triangulate(intr["A"], ext["A"], uv["A"], intr["B"], ext["B"], uv["B"])
        assert np.linalg.norm(np.asarray(est).reshape(-1)[:3] - truth) < 1.0, (option, seed)


def test_aim_angles_and_outer_face_measurements():
    rec = pl.recommend("gopro")
    for k in ("A", "B"):
        c = rec["cameras"][k]
        yaw, pitch = pl.aim_angles(c)
        # reconstruct the aim direction from yaw/pitch and compare with the look_at vector
        d = np.array(c["look_at"]) - np.array(c["pos"])
        d /= np.linalg.norm(d)
        e = np.array([math.cos(math.radians(pitch)) * math.cos(math.radians(yaw)),
                      math.cos(math.radians(pitch)) * math.sin(math.radians(yaw)),
                      math.sin(math.radians(pitch))])
        assert np.allclose(d, e, atol=1e-9)
        m = pl.operator_measurements(c["pos"])
        assert m["out_from_outer_face_in"] == pytest.approx(m["out_from_wall_in"]
                                                            - pl.WALL_THICKNESS_IN)
        assert m["along_from_outer_edge_in"] == pytest.approx(
            m["along_wall_from_corner_in"] + pl.WALL_THICKNESS_IN)
    assert pl.aim_angles({"pos": (0, 0, 0), "look_at": (0, 10, 0)}) == pytest.approx((90.0, 0.0))


def test_placement_doc_matches_recommend():
    text = (DOCS / "camera_placement.md").read_text(encoding="utf-8")
    for option in ("gopro", "usb"):
        rec = pl.recommend(option)
        for k in ("A", "B"):
            c = rec["cameras"][k]
            yaw, pitch = pl.aim_angles(c)
            m = pl.operator_measurements(c["pos"])
            assert f"{yaw:.0f} deg" in text and f"+{pitch:.0f} deg" in text
            assert f"{m['out_from_outer_face_in']:.1f} in out" in text
            assert f"{m['along_from_outer_edge_in']:.1f} in along" in text
    assert "`cam0`" in text and "`cam1`" in text
    assert "powered hub" not in text.replace("no hub, powered or not", "")
    assert "own USB port on the PC" in text and "INSIDE face" in text
    # the svg/png carry the same bearings
    svg = (DOCS / "camera_placement.svg").read_text(encoding="utf-8")
    yaw_a, _ = pl.aim_angles(pl.recommend("gopro")["cameras"]["A"])
    assert f"aim yaw {yaw_a:.0f} deg" in svg


# ------------------------------------------------ tag visibility term
OLD_POSES = {"A": (-78.0, 65.0, 36.0), "B": (65.0, 78.0, 36.0)}   # recommendation before the tag term


@pytest.mark.parametrize("option", ["gopro", "usb"])
def test_recommended_cameras_see_the_up_cell_tags(option):
    rec = pl.recommend(option)
    sc = rec["pair_score"]
    assert sc["tier"] == (True, True, True)          # arc + triangulation, tags, reference points
    assert sc["frac_in_both"] >= 0.9 and 60.0 <= sc["mean_angle_deg"] <= 120.0
    assert sc["tags_both"] and sc["refs_in_both"]
    _, centre, normal = pl._up_tag_geometry()
    # the sticker normal is (0, sin30, -cos30): faces down and toward the audience
    assert normal == pytest.approx([0.0, 0.5, -math.sqrt(3) / 2], abs=1e-6)
    for k in ("A", "B"):
        c = rec["cameras"][k]
        ray = np.array(c["pos"]) - centre
        ray /= np.linalg.norm(ray)
        ang = math.degrees(math.acos(float(ray @ normal)))
        assert ang < pl.TAG_MAX_ANGLE_DEG
        tv = rec["tags"][k]
        assert tv["sees"] and tv["in_image"] and tv["angle_deg"] == pytest.approx(ang, abs=1e-6)
        assert tv["min_edge_px"] >= pl.TAG_MIN_EDGE_PX


@pytest.mark.parametrize("option", ["gopro", "usb"])
def test_old_recommendation_could_not_read_the_tags(option):
    hfov = pl.HFOV_DEG[option]
    angles = []
    for pos in OLD_POSES.values():
        vc = pl._vcam(pos, (-13.0, 41.0, 61.0), hfov)
        tv = pl.tag_view(vc, pos)
        angles.append(tv["angle_deg"])
        assert not tv["sees"] and tv["angle_deg"] > pl.TAG_MAX_ANGLE_DEG
    assert min(angles) > 60.0                        # about 63 to 65 deg off the sticker normal


def test_height_candidates_and_wall_positions():
    assert min(pl.HEIGHTS_IN) == 12.0 and {12.0, 18.0, 24.0, 30.0, 36.0} <= set(pl.HEIGHTS_IN)
    cands = pl._candidates()
    assert len(cands) == len(set(cands))
    wall = [p for p in cands if p[1] == pl.MIN_RADIUS_IN]
    assert {p[0] for p in wall} >= set(range(-72, 73, pl.WALL_STEP_IN))
    assert all(max(abs(x), abs(y)) >= pl.MIN_RADIUS_IN - 1e-9 for x, y, _ in cands)


def test_hive_tags_visible_in_both_recommended_images():
    from hiveshot import tagkit

    tags = tagkit.up_cell_tag_corners("red", "audience")
    for option in ("gopro", "usb"):
        rec = pl.recommend(option)
        for k in ("A", "B"):
            cam = _cam(rec["cameras"][k], k)
            for tid, c in tags.items():
                u, v = cam.project(c)
                assert (u >= 10).all() and (u <= 1910).all() and (v >= 10).all() and (v <= 1070).all()

import math
from pathlib import Path

import cv2
import numpy as np
import pytest

from hiveshot import field_constants as fc
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
    # A ray running through the beam (x=RED_HIVE_X, z=46 crosses it near y=1) is blocked;
    # the same point seen from beside the launch area is clear.
    pts = np.array([[fc.RED_HIVE_X, 10.0, 46.0]])
    assert pl.occluded((fc.RED_HIVE_X, -78.0, 46.0), pts)[0]
    assert not pl.occluded((-78.0, 65.0, 36.0), np.array([[fc.RED_HIVE_X, 60.0, 40.0]]))[0]


@pytest.mark.parametrize("option,stem", [("usb", "camera_placement"),
                                          ("gopro", "camera_placement_gopro")])
def test_map_files_exist_and_agree(tmp_path, option, stem):
    """The default map is the Arducam (usb) option, the GoPro alternative has its own pair."""
    svg, png = DOCS / f"{stem}.svg", DOCS / f"{stem}.png"
    assert svg.exists() and png.exists()
    text = svg.read_text(encoding="utf-8")
    for label in ("CAM A", "CAM B", "CAM C"):
        assert label in text
    rec = pl.recommend(option)
    assert pl.OPTION_LABEL[option] in text and f"HFOV {rec['hfov_deg']:.0f} deg" in text
    for c in rec["cameras"].values():
        x, y, z = c["pos"]
        assert f"x={x:+.0f} y={y:+.0f}" in text and f"lens height {z:.0f} in" in text
    for k in ("A", "B"):
        yaw, pitch = pl.aim_angles(rec["cameras"][k])
        assert f"aim yaw {yaw:.0f} deg" in text and f"pitch {pitch:+.0f} deg" in text
    # tag reader is marked, kit tags 100-105 are drawn with their ids (104/105 optional)
    reader = rec["tag_reader"]
    assert reader in ("A", "B", "both")
    for k in ("A", "B"):
        marked = f"CAM {k} (tag reader)" in text
        assert marked == (reader in (k, "both"))
    assert "TAG READER" in text
    for tid in range(100, 104):
        assert f">{tid}</text>" in text
    assert ">104 opt</text>" in text and ">105 opt</text>" in text
    # regenerating gives the same SVG (map and recommend() cannot drift apart)
    pl.write_map(option, tmp_path / "m.svg", tmp_path / "m.png")
    assert (tmp_path / "m.svg").read_text(encoding="utf-8") == text
    img = cv2.imread(str(png))
    assert img.shape[:2] == (1600, 1600)
    assert (cv2.imread(str(tmp_path / "m.png")) == img).all()


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
    yaw_a, _ = pl.aim_angles(pl.recommend("usb")["cameras"]["A"])
    assert f"aim yaw {yaw_a:.0f} deg" in svg


# ------------------------------------------------ tag visibility term
# recommendation before the tag term (drawn for red at -X), mirrored in X for red at +X
OLD_POSES = {"A": (78.0, 65.0, 36.0), "B": (-65.0, 78.0, 36.0)}


@pytest.mark.parametrize("option", ["gopro", "usb"])
def test_recommendation_meets_the_hard_constraints(option):
    rec = pl.recommend(option)
    sc = rec["pair_score"]
    # tier: arc + triangulation >= 75, robot-free rays, >= 1 tag reader, printed kit readable,
    # 8 reference points, not both cameras on the audience wall, (both read tags: preferred)
    assert all(sc["tier"][:6]), sc["tier"]
    assert sc["frac_in_both"] >= 0.9
    assert pl.MIN_TRI_DEG <= sc["mean_angle_deg"] <= 120.0
    assert not sc["both_on_audience_wall"] and sc["kit_both"]
    assert all(c["height_in"] >= 20.0 for c in rec["cameras"].values())
    _, centre, normal = pl._up_tag_geometry()
    # the sticker normal is (0, sin30, -cos30): faces down and toward the audience
    assert normal == pytest.approx([0.0, 0.5, -math.sqrt(3) / 2], abs=1e-6)
    readers = []
    for k in ("A", "B"):
        c = rec["cameras"][k]
        ray = np.array(c["pos"]) - centre
        ray /= np.linalg.norm(ray)
        ang = math.degrees(math.acos(float(ray @ normal)))
        tv = rec["tags"][k]
        assert tv["angle_deg"] == pytest.approx(ang, abs=1e-6)
        if tv["sees"]:
            readers.append(k)
            assert ang < pl.TAG_MAX_ANGLE_DEG and tv["in_image"]
            assert tv["min_edge_px"] >= pl.TAG_MIN_EDGE_PX
        rv = rec["robot"][k]
        assert rv["free"] >= pl.ROBOT_MIN_FREE and rv["tag_free"] == 1.0
        assert rv == pl.robot_view(c["pos"])
    assert readers and rec["tag_reader"] == ("both" if len(readers) == 2 else readers[0])


@pytest.mark.parametrize("option", ["gopro", "usb"])
def test_both_tags_alternative_is_reported_not_recommended(option):
    rec = pl.recommend(option)
    alt = rec["both_tags_alternative"]
    assert alt["tag_reader"] == "both" and alt["pair_score"]["tags_both"]
    for k in ("A", "B"):
        assert alt["tags"][k]["sees"] and alt["tags"][k]["angle_deg"] < pl.TAG_MAX_ANGLE_DEG
        assert alt["cameras"][k]["height_in"] >= 20.0
        assert alt["robot"][k]["free"] >= pl.ROBOT_MIN_FREE
    # it is only ever chosen over the recommendation if it is no worse on the hard
    # constraints; the recommendation must not give up triangulation angle for tag reading
    assert rec["pair_score"]["mean_angle_deg"] >= pl.MIN_TRI_DEG
    assert alt["pair_score"]["both_on_audience_wall"] or alt["pair_score"]["mean_angle_deg"] <= \
        rec["pair_score"]["mean_angle_deg"] + 1e-9
    assert (alt["cameras"]["A"]["pos"], alt["cameras"]["B"]["pos"]) != (
        rec["cameras"]["A"]["pos"], rec["cameras"]["B"]["pos"])


@pytest.mark.parametrize("option", ["gopro", "usb"])
def test_old_recommendation_could_not_read_the_tags(option):
    hfov = pl.HFOV_DEG[option]
    angles = []
    for pos in OLD_POSES.values():
        vc = pl._vcam(pos, (13.0, 41.0, 61.0), hfov)
        tv = pl.tag_view(vc, pos)
        angles.append(tv["angle_deg"])
        assert not tv["sees"] and tv["angle_deg"] > pl.TAG_MAX_ANGLE_DEG
    assert min(angles) > 60.0                        # about 63 to 65 deg off the sticker normal


def test_height_candidates_and_wall_positions():
    assert min(pl.HEIGHTS_IN) == 20.0                # UBeesize MT60 practical minimum
    assert {20.0, 24.0, 30.0, 36.0, 48.0, 58.0} <= set(pl.HEIGHTS_IN) and max(pl.HEIGHTS_IN) == 58.0
    cands = pl._candidates()
    assert len(cands) == len(set(cands))
    wall = [p for p in cands if p[1] == pl.MIN_RADIUS_IN]
    assert {p[0] for p in wall} >= set(range(-72, 73, pl.WALL_STEP_IN))
    assert all(max(abs(x), abs(y)) >= pl.MIN_RADIUS_IN - 1e-9 for x, y, _ in cands)
    assert all(p[2] >= 20.0 for p in cands)


def test_hive_tags_visible_in_both_recommended_images():
    from hiveshot import tagkit

    tags = tagkit.up_cell_tag_corners("red", "audience")
    for option in ("gopro", "usb"):
        rec = pl.recommend(option)
        for k in ("A", "B"):
            cam = _cam(rec["cameras"][k], k)
            for c in tags.values():
                u, v = cam.project(c)
                assert (u >= 10).all() and (u <= 1910).all() and (v >= 10).all() and (v <= 1070).all()


def test_calibration_doc_pixel_table_matches_recommend():
    """The percent-of-image positions in calibration.md equal the recomputed projections."""
    import re

    from hiveshot import calib_targets

    text = (DOCS / "calibration.md").read_text(encoding="utf-8")
    pts = [p for _, p in calib_targets.field_reference_points()]
    rows = {}
    for ln in text.splitlines():
        m = re.match(r"\| ([1-8]) \| .*`cam0`: (\d+)/(\d+) or (\d+)/(\d+)\. `cam1`: (\d+)/(\d+) or "
                     r"(\d+)/(\d+) \|", ln)
        if m:
            rows[int(m.group(1))] = [int(g) for g in m.groups()[1:]]
    assert sorted(rows) == list(range(1, 9))
    for opt_i, option in enumerate(("gopro", "usb")):
        rec = pl.recommend(option)
        for cam_i, k in enumerate(("A", "B")):
            cam = _cam(rec["cameras"][k], k)
            u, v = cam.project(np.array(pts))
            for n in range(1, 9):
                got = rows[n][cam_i * 4 + opt_i * 2: cam_i * 4 + opt_i * 2 + 2]
                assert abs(100 * u[n - 1] / 1920 - got[0]) <= 1.0, (option, k, n)
                assert abs(100 * v[n - 1] / 1080 - got[1]) <= 1.0, (option, k, n)


def test_recommended_aim_has_slack_and_same_spots_for_both_options():
    """Each camera's aim sits inside the range that keeps the printed kit, the 8 reference
    points (and, for a tag reader, the CELL tags) in view, with at least 3 deg to spare in yaw
    and pitch; both lens options use the same tripod spots."""
    for k in ("A", "B"):
        assert pl.recommend("gopro")["cameras"][k]["pos"] == pl.recommend("usb")["cameras"][k]["pos"]
    for option in ("gopro", "usb"):
        rec = pl.recommend(option)
        for k in ("A", "B"):
            c = rec["cameras"][k]
            need = rec["tags"][k]["sees"]
            assert pl._aim_ok(c["pos"], c["look_at"], c["hfov_deg"], need)
            for dy, dp in ((3, 0), (-3, 0), (0, 3), (0, -3)):
                look = pl._rotated_aim(c["pos"], c["look_at"], dy, dp)
                assert pl._aim_ok(c["pos"], look, c["hfov_deg"], need), (option, k, dy, dp)
        assert rec["pair_score"]["kit_both"]


# ------------------------------------------------ robot occlusion
def test_robot_box_blocks_rays_through_it_and_only_those():
    smp = pl._robot_samples()
    assert set(np.unique(smp["kind"])) == {"ball", "cell", "tag"}
    # a camera right behind a robot (same launch point, low) cannot see targets beyond it
    shot0 = smp["shot"] == 0
    lo, hi = smp["lo"][shot0][0], smp["hi"][shot0][0]
    centre = 0.5 * (lo + hi)
    behind = centre + np.array([0.0, 30.0, -11.0])
    blocked = pl.robot_blocked(behind, {k: v[shot0] for k, v in smp.items()})
    cell = smp["kind"][shot0] == "cell"
    assert blocked[cell][0]          # the CELL lies on the far side of the robot from here
    above = centre + np.array([0.0, 30.0, 200.0])
    assert not pl.robot_blocked(above, {k: v[shot0] for k, v in smp.items()}).any()
    # ball positions still inside the robot box are not samples
    for i in np.where(smp["kind"] == "ball")[0]:
        p, a, b = smp["targets"][i], smp["lo"][i], smp["hi"][i]
        assert not ((p >= a).all() and (p <= b).all())


def test_robot_box_size_extension_and_window(monkeypatch):
    assert pl.ROBOT_BOX_IN == (18.0, 18.0, 24.0) and pl.ROBOT_WINDOW_S == 0.3
    smp = pl._robot_samples()
    half = 9.0 + pl.ROBOT_EXTENSION_IN
    assert np.allclose(smp["hi"][:, 0] - smp["lo"][:, 0], 2 * half)
    assert np.allclose(smp["hi"][:, 2], 24.0) and np.allclose(smp["lo"][:, 2], 0.0)
    balls = smp["targets"][smp["kind"] == "ball"]
    assert balls.shape[0] > 0
    monkeypatch.setattr(pl, "ROBOT_EXTENSION_IN", 6.0)
    pl._robot_samples.cache_clear()
    try:
        wide = pl._robot_samples()
        assert np.allclose(wide["hi"][:, 0] - wide["lo"][:, 0], 2 * (9.0 + 6.0))
    finally:
        monkeypatch.undo()
        pl._robot_samples.cache_clear()


@pytest.mark.parametrize("option", ["gopro", "usb"])
def test_recommended_cameras_have_free_rays(option):
    rec = pl.recommend(option)
    for k in ("A", "B"):
        rv = pl.robot_view(rec["cameras"][k]["pos"])
        assert rv["free"] >= 0.9 and rv["cell_free"] == 1.0 and rv["tag_free"] == 1.0


def test_geometry_comes_from_field_py():
    """The map and tag term use hiveshot.field, not copies of its numbers: no 24.25 / 21.54 /
    -12.75 literals in placement.py."""
    src = (Path(pl.__file__)).read_text(encoding="utf-8")
    for lit in ("24.25", "21.54", "12.75", "49.9"):
        assert lit not in src, lit
    _, centre, _ = pl._up_tag_geometry()
    assert centre[0] == pytest.approx(fc.RED_HIVE_X)
    assert centre[1] == pytest.approx(13.10, abs=0.05) and centre[2] == pytest.approx(49.79, abs=0.05)

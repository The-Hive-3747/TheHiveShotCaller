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
    r = pl.MIN_RADIUS_IN
    c = pl.candidate_positions(r, (36, 58), range(0, 360, 30))
    assert len(c) == 24
    assert all(max(abs(x), abs(y)) >= r - 1e-9 for x, y, _ in c)
    # the coordinate that sets the distance from the wall is exactly the radius
    assert all(max(abs(x), abs(y)) == r for x, y, _ in c)
    with pytest.raises(ValueError):
        pl.candidate_positions(70, (36,), (0,))
    # lens plumb spot 12 in from the OUTSIDE face of a 1.5 in wall; legs of a ~20 in radius
    # tripod with one leg pointing away from the wall put the nearest feet 10 in toward it
    assert pl.MIN_RADIUS_IN - pl.WALL_HALF - pl.WALL_THICKNESS_IN == pytest.approx(12.0)
    assert 12.0 > 20.0 / 2


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
    # tag reader(s) marked, kit tags 100-103 drawn from the real frame positions with their ids
    reader = rec["tag_reader"]
    assert reader in ("A", "B", "both")
    for k in ("A", "B"):
        marked = f"CAM {k} (tag reader)" in text
        assert marked == (reader in (k, "both"))
    assert "TAG READER" in text
    for tid in range(100, 104):
        assert f">{tid}</text>" in text
    assert ">104" not in text and "opt</text>" not in text      # no optional bar tags any more
    # the four FLOWERs are drawn with their label
    assert text.count(">FLOWER</text>") == 4 and text.count("<circle") >= 4 + 3 * 2
    # the frame is the CAD A-frame (foot bars, legs, crossbar), not a box
    assert text.count("<line ") > 20
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
    assert all(sc["tier"][:5]), sc["tier"]
    assert sc["tier"][5] == sc["tags_both"]          # both read the CELL tags: preferred, not required
    assert sc["kit_both"]
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
def test_both_tags_alternative_is_reported(option):
    rec = pl.recommend(option)
    alt = rec["both_tags_alternative"]
    for k in ("A", "B"):
        assert alt["cameras"][k]["height_in"] >= 20.0
        assert alt["robot"][k]["free"] >= pl.ROBOT_MIN_FREE
        assert "angle_deg" in alt["tags"][k]
    # with sticker tags required to be >= TAG_MIN_EDGE_PX no pair has BOTH cameras reading the
    # CELL tags while meeting the other hard rules, so the best "both read" pair is the
    # recommendation itself and exactly one camera (B, `cam1`) is the tag reader
    assert rec["tag_reader"] in ("A", "B", "both")
    if not alt["pair_score"]["tags_both"]:
        assert (alt["cameras"]["A"]["pos"], alt["cameras"]["B"]["pos"]) == (
            rec["cameras"]["A"]["pos"], rec["cameras"]["B"]["pos"])
    # it must never beat the recommendation on triangulation angle
    assert alt["pair_score"]["mean_angle_deg"] <= rec["pair_score"]["mean_angle_deg"] + 1e-9


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


# ------------------------------------------------ real frame, tripod feet, kit geometry
def test_frame_is_the_cad_a_frame_and_kit_uses_real_features():
    from hiveshot import field, tagkit

    segs = field._frame_segments()
    assert max(max(a[2], b[2]) for a, b in segs) <= 44.4          # no 64 in box, ridge/cradles only
    lines = pl._frame_lines()
    assert len(lines) >= 12 and all(len(p) == 2 for seg in lines for p in seg)
    feats = dict(field.frame_reference_points())
    assert len(feats) == 7
    # kit tags are anchored on those features: crossbar ends and audience-side base corners
    quad, pn = field.logo_panel_face("audience")
    for tid, sx in ((100, -1), (101, 1)):                 # lying on the slanted logo panel
        c = tagkit.tag_corners_xyz(tid)
        assert np.allclose((c - quad[0]) @ pn, 0.0, atol=1e-3)      # on the panel plane
        assert np.sign(c[:, 0].mean()) == sx and abs(c[:, 0]).max() <= quad[3][0]
    for tid, name in ((102, "Frame base corner (-X, +Y)"), (103, "Frame base corner (+X, +Y)")):
        assert abs(tagkit.tag_corners_xyz(tid)[:, 0]).max() == pytest.approx(abs(feats[name][0]))
    # nothing recommended overlaps the CELL sticker in the picture
    for option in ("gopro", "usb"):
        rec = pl.recommend(option)
        for k in ("A", "B"):
            kit = rec["tags"][k]["kit"]["tags"]
            assert not any(d["overlaps_sticker"] for d in kit.values() if d["ok"])
            assert rec["tags"][k]["kit"]["n_ok"] >= pl.KIT_MIN_TAGS


def test_doc_states_tripod_feet_field_size_and_tag_tolerance():
    place = (DOCS / "camera_placement.md").read_text(encoding="utf-8")
    cal = (DOCS / "calibration.md").read_text(encoding="utf-8")
    assert "one leg pointing straight away from the wall" in place
    assert "12.0 in out from the OUTSIDE face" in place or "12 in out from the OUTSIDE face" in place
    assert "`field_size_in`" in place and "default 144 in" in place and "wall to wall" in place
    assert "141.35" in place
    assert "within 0.25 in" in place and "within 0.25 in" in cal
    assert "Cross-check" in cal and "out-of-sample" in cal and "in-sample" in cal
    for needle in ("0.25 in, 0.5 deg", "0.5 in, 1 deg", "1 in, 2 deg"):
        assert needle in place and needle in cal
    assert "alliance area" in place.lower() and "37 in clear" in place
    assert "FLOWER" in place and "4.1 %" in place
    assert "drive team stands between" not in place and "drive team stands between" not in cal
    assert "in-sample" in cal and "camera B" in cal and "3 px" in cal
    # no leftover mention of the non-existent box frame as a target
    assert "frame top corner" not in cal.replace("frame \"top corners\" (a box", "")


# ------------------------------------------------ FLOWER occlusion
def test_flower_cylinders_block_rays(monkeypatch):
    from hiveshot import field

    fl = field.flower_positions()
    assert len(fl) == 4
    x, y = fl[0]["xy"]
    r = fl[0]["radius"]
    cam = np.array([x + 40.0, y, 10.0])
    through = np.array([[x - 40.0, y, 10.0]])                 # straight through the cylinder at z = 10
    above = np.array([[x - 40.0, y, 60.0]])
    beside = np.array([[x - 40.0, y + 2 * r + 6.0, 10.0]])
    assert pl.flower_blocked(cam, through)[0]
    assert not pl.flower_blocked(cam, above)[0]               # passes over z > 22.65 at the flower
    assert not pl.flower_blocked(cam, beside)[0]
    assert not pl.flower_blocked(np.array([x + 40.0, y, 40.0]), np.array([[x + 20.0, y, 40.0]]))[0]
    monkeypatch.setattr(pl, "USE_FLOWERS", False)
    assert not pl.flower_blocked(cam, through)[0]


def test_flower_effect_on_camera_a():
    """The audience-wall FLOWER clips about 4 % of the ball rays from the corner spot the
    recommendation used before the FLOWERs were modeled; the recommended spot clips under 2 %."""
    pts = pl._stack(pl.sample_trajectories())
    old_a = (-72.0, pl.MIN_RADIUS_IN, 20.0)
    assert 0.03 <= pl.flower_blocked(old_a, pts).mean() <= 0.06
    for option in ("gopro", "usb"):
        rec = pl.recommend(option)
        assert pl.flower_blocked(rec["cameras"]["A"]["pos"], pts).mean() < 0.02
        assert pl.flower_blocked(rec["cameras"]["B"]["pos"], pts).mean() < 0.02


def test_alliance_areas_are_not_camera_spots():
    from hiveshot import placement

    cands = placement._candidates()
    assert all(not placement._in_alliance_area(p) for p in cands)
    # a side-wall spot at the audience corner (outside the 97 in wide alliance area) is allowed
    assert placement._in_alliance_area((-85.5, 0.0, 30.0)) and not placement._in_alliance_area(
        (-85.5, 70.0, 30.0))
    # the recommendation keeps its cameras ~37 in clear (along y) of the alliance area ends
    for option in ("gopro", "usb"):
        for k in ("A", "B"):
            x, y, _ = pl.recommend(option)["cameras"][k]["pos"]
            assert abs(y) - placement.ALLIANCE_AREA_HALF_Y_IN >= 36.0


def test_calibration_doc_button_names_and_intrinsics_guidance():
    cal = (DOCS / "calibration.md").read_text(encoding="utf-8")
    for name in ("Auto-calibrate all", "**Auto-calibrate**", "**Cross-check**", "**Start intrinsics**",
                 "**Stop intrinsics**", "**Refresh image**", "**Solve extrinsics**", "**Undo point**",
                 "**Clear**", "**Detect and preview**", "**Learn**", "**Start pipeline and session**",
                 "**Download checkerboard PDF**", "**Open printable tag sheet (PDF)**"):
        assert name in cal, name
    for step in ("1. Cameras", "2. Lens", "3. Tags", "4. Verify HIVE tags", "5. Colors", "6. Done"):
        assert step in cal, step
    assert "1.5 to 3 ft" in cal and "+-30 degrees" in cal and "a third of the picture" in cal
    assert "20 seconds" in cal and "under 1 px" in cal and "1 to 2 px" in cal
    assert "far HIVE tags are not visible from the audience-side cameras" in cal
    assert "audience-up" in cal

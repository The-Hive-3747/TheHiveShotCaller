"""Tag-kit calibration: render the four tags through a virtual camera, detect, solve."""
from __future__ import annotations

import cv2
import numpy as np
import pytest

from hiveshot import calib, calib_targets, field, tagkit
from hiveshot import placement as pl
from hiveshot.synth import VirtualCamera

W, H = 1920, 1080


def _vcam(option, k):
    c = pl.recommend(option)["cameras"][k]
    return VirtualCamera(*pl.camera_from_pose(c["pos"], c["look_at"], c["hfov_deg"], W, H,
                                              "cam0" if k == "A" else "cam1"))


def render_tags(cam, hide=(), seed=0, noise=2.0):
    """Synthetic frame: gray background, each kit tag (with a white quiet zone) warped onto
    the quad its 3-D corners project to."""
    img = np.full((H, W, 3), 110, np.uint8)
    pad, n = 120, 400                       # quiet zone / marker size in source pixels
    tot = n + 2 * pad
    for t in tagkit.KIT_TAGS:
        if t.id in hide:
            continue
        marker = tagkit.render_marker(t.id, n)
        src = np.full((tot, tot), 255, np.uint8)
        src[pad:pad + n, pad:pad + n] = marker
        u, v = cam.project(tagkit.tag_corners_xyz(t))
        dst = np.c_[u, v].astype(np.float32)
        s = np.float32([[pad, pad], [pad + n, pad], [pad + n, pad + n], [pad, pad + n]])
        Hm = cv2.getPerspectiveTransform(s, dst)
        warped = cv2.warpPerspective(src, Hm, (W, H), flags=cv2.INTER_AREA,
                                     borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        mask = cv2.warpPerspective(np.full((tot, tot), 255, np.uint8), Hm, (W, H),
                                   borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        m = mask > 127
        img[m] = warped[m][:, None]
    rng = np.random.default_rng(seed)
    img = np.clip(img.astype(np.float32) + rng.normal(0, noise, img.shape), 0, 255)
    return cv2.GaussianBlur(img.astype(np.uint8), (3, 3), 0.6)


def _rot_deg(ea, eb):
    Ra = cv2.Rodrigues(np.array(ea.rvec))[0]
    Rb = cv2.Rodrigues(np.array(eb.rvec))[0]
    return float(np.degrees(np.arccos(np.clip((np.trace(Ra.T @ Rb) - 1) / 2, -1, 1))))


def _pos(ext):
    R = cv2.Rodrigues(np.array(ext.rvec))[0]
    return -R.T @ np.array(ext.tvec)


# ------------------------------------------------------------------ definitions
def test_kit_definition():
    assert [t.id for t in tagkit.KIT_TAGS] == [100, 101, 102, 103]
    assert all(t.size_in == 4.0 for t in tagkit.KIT_TAGS)
    names = [n for n, _ in calib_targets.field_reference_points()][4:]
    assert [t.point_name for t in tagkit.KIT_TAGS] == names
    ref = dict(calib_targets.field_reference_points())
    for t in tagkit.KIT_TAGS:
        c = tagkit.tag_corners_xyz(t)
        assert c.shape == (4, 3)
        # vertical plane facing +Y: constant y equal to the frame corner's y
        assert np.allclose(c[:, 1], ref[t.point_name][1])
        # square of 4.0 in, edges follow the aruco order TL, TR, BR, BL (upright = +Z)
        assert np.allclose(np.linalg.norm(c[1] - c[0]), 4.0)
        assert np.allclose(np.linalg.norm(c[2] - c[1]), 4.0)
        assert c[0, 2] == pytest.approx(c[1, 2]) and c[0, 2] > c[3, 2]
        assert c[1, 0] < c[0, 0]            # right side of the tag is toward -X
        # flush mount: the outer top corner of the tag is the frame corner point
        outer = c[0] if ref[t.point_name][0] > 0 else c[1]
        assert np.allclose(outer, ref[t.point_name])
    js = tagkit.tags_json()
    assert [j["id"] for j in js] == [100, 101, 102, 103]
    assert set(js[0]) >= {"id", "size_in", "name", "xyz_center", "corners_xyz"}
    assert np.allclose(js[0]["corners_xyz"], tagkit.tag_corners_xyz(100))


def test_tag_sheet_pdf(tmp_path):
    p = tagkit.write_tag_sheet_pdf(tmp_path / "tags.pdf")
    data = p.read_bytes()
    assert data.startswith(b"%PDF") and data.rstrip().endswith(b"%%EOF")
    assert data.count(b"/Type /Page ") == 2
    assert tagkit.tag_sheet_pdf_bytes() == data
    page = cv2.imread(str(tmp_path / "tags_p1.png"), cv2.IMREAD_GRAYSCALE)
    assert page.shape == (2550, 3300)       # letter landscape at 300 dpi
    # the printed tags decode to their ids, 4.00 in = 1200 px
    found = {}
    for pn in (1, 2):
        img = cv2.imread(str(tmp_path / f"tags_p{pn}.png"), cv2.IMREAD_GRAYSCALE)
        for d in calib.detect_apriltags(img):
            found[d["id"]] = d["corners"]
    assert sorted(found) == [100, 101, 102, 103]
    for c in found.values():
        assert np.linalg.norm(c[1] - c[0]) == pytest.approx(1200, abs=2)


# ------------------------------------------------------------------ detect + solve
@pytest.mark.parametrize("option", ["gopro", "usb"])
def test_detect_and_solve_recovers_pose(option):
    cams = {k: _vcam(option, k) for k in "AB"}
    est = {}
    for k, cam in cams.items():
        img = render_tags(cam, seed=1)
        ids = sorted(d["id"] for d in calib.detect_apriltags(img))
        assert ids == [100, 101, 102, 103], (option, k, ids)
        ext, info = calib.solve_extrinsics_from_tags(cam.intr, img, tagkit.tag_defs(), cam.cam_id)
        assert info["tags_used"] == [100, 101, 102, 103] and info["tags_missing"] == []
        assert info["reprojection_px"] < 1.0
        assert np.linalg.norm(_pos(ext) - _pos(cam.extr)) < 0.5, (option, k)
        assert _rot_deg(ext, cam.extr) < 0.3, (option, k)
        est[k] = ext
    # CELL opening center triangulated from the two tag-calibrated cameras
    truth, _ = field.cell_opening_plane("red", "audience", field.HiveState("red", "audience"))
    ua = np.array([a[0] for a in cams["A"].project(truth)])
    ub = np.array([a[0] for a in cams["B"].project(truth)])
    xyz, res = calib.triangulate(cams["A"].intr, est["A"], ua, cams["B"].intr, est["B"], ub)
    assert np.linalg.norm(np.asarray(xyz).reshape(-1)[:3] - truth) < 1.0


def test_three_tags_still_solve_one_tag_raises():
    cam = _vcam("gopro", "B")
    defs = tagkit.tag_defs()
    img3 = render_tags(cam, hide=(102,), seed=2)
    ext, info = calib.solve_extrinsics_from_tags(cam.intr, img3, defs, "cam1")
    assert info["tags_used"] == [100, 101, 103] and info["tags_missing"] == [102]
    assert np.linalg.norm(_pos(ext) - _pos(cam.extr)) < 1.0
    assert _rot_deg(ext, cam.extr) < 0.6

    img2 = render_tags(cam, hide=(102, 103), seed=2)
    ext2, info2 = calib.solve_extrinsics_from_tags(cam.intr, img2, defs, "cam1")
    assert info2["tags_used"] == [100, 101]

    img1 = render_tags(cam, hide=(101, 102, 103), seed=2)
    with pytest.raises(ValueError, match=r"only 1 tag visible: 100; need 2"):
        calib.solve_extrinsics_from_tags(cam.intr, img1, defs, "cam1")
    with pytest.raises(ValueError, match="no known tags visible"):
        calib.solve_extrinsics_from_tags(cam.intr, render_tags(cam, hide=(100, 101, 102, 103)),
                                         defs, "cam1")
    # min_tags is respected
    ext1, _ = calib.solve_extrinsics_from_tags(cam.intr, img2, defs, "cam1", min_tags=2)
    with pytest.raises(ValueError, match="need 3"):
        calib.solve_extrinsics_from_tags(cam.intr, img2, defs, "cam1", min_tags=3)
    assert ext1 is not None


def test_calibration_doc_describes_tag_kit():
    from pathlib import Path

    text = (Path(__file__).resolve().parent.parent / "docs" / "calibration.md").read_text(
        encoding="utf-8")
    for needle in ("/api/calib/tags.pdf", "Auto-calibrate", "label up", "4.00 in",
                   "only 1 tag visible: 100; need 2", "3B"):
        assert needle in text, needle
    for t in tagkit.KIT_TAGS:
        assert f"| {t.id} |" in text


# ------------------------------------------------------------------ HIVE tags: learn + infer
from hiveshot import field_constants as fc  # noqa: E402


def _row_tags(cluster, y, z, hive_x=fc.RED_HIVE_X, upside_down=False):
    """Synthetic tag row: four 3.25 in tags in a vertical plane facing +Y, ids ascending
    left to right as seen from the audience side (+X is on the viewer's left)."""
    s = fc.APRILTAG_SIZE / 2
    out = {}
    for tid, off in zip(fc.HIVE_TAG_CLUSTERS[cluster], fc.HIVE_TAG_ROW_OFFSETS_IN, strict=True):
        cx = hive_x - off
        c = np.array([[cx + s, y, z + s], [cx - s, y, z + s],
                      [cx - s, y, z - s], [cx + s, y, z - s]])
        out[tid] = c[[2, 3, 0, 1]] if upside_down else c      # rolled 180 deg: DOWN cell
    return out


def _state(up_audience: bool):
    ya = field.OPENING_CENTER_ABS_Y
    za, zf = (fc.HIVE_TAG_ROW_HEIGHT_UP_IN, fc.HIVE_TAG_ROW_HEIGHT_DOWN_IN)
    if not up_audience:
        za, zf = zf, za
    tags = _row_tags("red_audience", ya, za, upside_down=not up_audience)
    tags.update(_row_tags("red_far", -ya, zf, upside_down=up_audience))
    return tags


def render_tag_dict(cam, tags, seed=0, noise=2.0):
    """Like render_tags for arbitrary tags; all quiet zones are drawn first so neighbouring
    tags in a row are not overwritten by each other's white margin."""
    img = np.full((H, W, 3), 110, np.uint8)
    n = 400
    s = np.float32([[0, 0], [n, 0], [n, n], [0, n]])
    for c in tags.values():                    # white halo (half a tag wide, capped)
        u, v = cam.project(c)
        q = np.c_[u, v]
        ctr = q.mean(axis=0)
        halo = (ctr + (q - ctr) * 1.25).astype(np.int32)
        cv2.fillConvexPoly(img, halo, (255, 255, 255))
    for tid, c in tags.items():
        u, v = cam.project(c)
        Hm = cv2.getPerspectiveTransform(s, np.c_[u, v].astype(np.float32))
        warped = cv2.warpPerspective(tagkit.render_marker(tid, n), Hm, (W, H),
                                     flags=cv2.INTER_AREA, borderValue=0)
        mask = cv2.warpPerspective(np.full((n, n), 255, np.uint8), Hm, (W, H),
                                   borderValue=0) > 250
        img[mask] = warped[mask][:, None]
    rng = np.random.default_rng(seed)
    img = np.clip(img.astype(np.float32) + rng.normal(0, noise, img.shape), 0, 255)
    return cv2.GaussianBlur(img.astype(np.uint8), (3, 3), 0.6)


def _fixed_cams():
    """Two cameras at fixed poses that see the generic synthetic rows below (the recommended
    poses are chosen for the real up-CELL stickers, not for these test rows)."""
    out = {}
    for k, pos in (("A", (-78.0, 65.0, 36.0)), ("B", (65.0, 78.0, 36.0))):
        out[k] = VirtualCamera(*pl.camera_from_pose(pos, (-13.0, 41.0, 61.0), 86.0, W, H,
                                                    "cam0" if k == "A" else "cam1"))
    return out


@pytest.fixture(scope="module")
def hive_world():
    cams = _fixed_cams()
    world = {}
    for key, up_aud in (("red/audience", True), ("red/far", False)):
        tags = _state(up_aud)
        imgs = {k: render_tag_dict(cams[k], tags, seed=7) for k in "AB"}
        learned, info = tagkit.learn_hive_tags(cams["A"].intr, cams["A"].extr, imgs["A"],
                                               cams["B"].intr, cams["B"].extr, imgs["B"])
        world[key] = {"tags": tags, "imgs": imgs, "learned": learned, "info": info}
    return cams, world


@pytest.mark.parametrize("key", ["red/audience", "red/far"])
def test_learn_hive_tags_corner_error(hive_world, key):
    _, world = hive_world
    w = world[key]
    assert w["info"]["ids_learned"] == sorted(w["tags"]), w["info"]
    assert set(w["info"]["visible_per_camera"]) == {"cam0", "cam1"}
    assert w["info"]["max_residual_in"] < 0.5
    for tid, truth in w["tags"].items():
        err = np.linalg.norm(w["learned"][tid] - truth, axis=1).max()
        assert err < 0.5, (key, tid, err)


def test_row_heights_and_defs(hive_world):
    _, world = hive_world
    up = world["red/audience"]["learned"]
    assert tagkit.row_height_in(up, "red_audience") == pytest.approx(50.2, abs=0.3)
    assert tagkit.row_height_in(up, "red_far") == pytest.approx(35.0, abs=0.3)
    assert tagkit.row_height_in(up, "blue_far") is None
    d = tagkit.hive_tag_defs_from_learned({**up, 5: np.zeros((4, 3))})
    assert sorted(d) == sorted(up) and 5 not in d


def test_resolve_cam_a_from_learned_hive_tags_only(hive_world):
    cams, world = hive_world
    cam = cams["A"]
    for key in world:
        defs = tagkit.hive_tag_defs_from_learned(world[key]["learned"])
        ext, info = calib.solve_extrinsics_from_tags(cam.intr, world[key]["imgs"]["A"], defs,
                                                     "cam0", min_tags=2)
        assert len(info["tags_used"]) == 8
        assert np.linalg.norm(_pos(ext) - _pos(cam.extr)) < 0.5, key
        assert _rot_deg(ext, cam.extr) < 0.3, key


def _dets(world, key):
    return {("cam0" if k == "A" else "cam1"): calib.detect_apriltags(world[key]["imgs"][k])
            for k in "AB"}


def test_infer_hive_state(hive_world):
    cams, world = hive_world
    by_state = {k: w["learned"] for k, w in world.items()}
    calib_pc = {"cam0": (cams["A"].intr, cams["A"].extr), "cam1": (cams["B"].intr, cams["B"].extr)}
    for key in world:
        got, conf = tagkit.infer_hive_state(by_state, _dets(world, key), calib_pc)
        assert got == key and conf > 0.8, (key, got, conf)
        # one camera only (single-camera PnP row height)
        one = {"cam0": _dets(world, key)["cam0"]}
        got1, conf1 = tagkit.infer_hive_state(by_state, one, {"cam0": calib_pc["cam0"]})
        assert got1 == key and conf1 > 0.5, (key, got1, conf1)
    # the row height decides, not just the ids: both states show the same ids
    assert (sorted(d["id"] for d in _dets(world, "red/audience")["cam0"])
            == sorted(d["id"] for d in _dets(world, "red/far")["cam0"]))
    # no calibration: ids-only fallback is low confidence; nothing visible -> (None, 0)
    key_ids, conf_ids = tagkit.infer_hive_state(by_state, _dets(world, "red/far"), None)
    assert conf_ids <= 0.6
    assert tagkit.infer_hive_state(by_state, {"cam0": []}, calib_pc) == (None, 0.0)


# ------------------------------------------------------------------ computed up-cell tags
def test_up_cell_tag_geometry():
    from hiveshot import field

    tags = tagkit.up_cell_tag_corners("red", "audience")
    assert sorted(tags) == [34, 35, 36, 37]
    allc = np.array([tags[k] for k in sorted(tags)])
    ctr = allc.reshape(-1, 3).mean(axis=0)
    # official numbers: row center 7.188 in behind the opening's bottom edge along the floor,
    # about 50 in high; sticker normal (0, sin30, -cos30)
    st = field.HiveState("red", "audience")
    origin, _, udep, nrm = field.cell_floor_frame("red", "audience", st)
    want = origin + fc.TAG_ROW_FROM_CELL_FRONT * udep
    assert ctr[1:] == pytest.approx(want[1:], abs=0.3) and ctr[0] == pytest.approx(fc.RED_HIVE_X)
    assert ctr[2] == pytest.approx(49.9, abs=0.3)
    for tid, off in zip(sorted(tags), fc.HIVE_TAG_ROW_OFFSETS_IN, strict=True):
        c = tags[tid]
        assert np.linalg.norm(c[1] - c[0]) == pytest.approx(fc.APRILTAG_SIZE)
        # ids ascend toward image-right, which is -X for the audience-up cell
        assert c.mean(axis=0)[0] == pytest.approx(fc.RED_HIVE_X - off)
        n = np.cross(c[1] - c[0], c[0] - c[3])
        n /= np.linalg.norm(n)
        assert n == pytest.approx([0.0, 0.5, -np.sqrt(3) / 2], abs=1e-6)
        up = c[0] - c[3]
        assert up[2] > 0                         # upright for the UP cell
    for which in ("audience", "far"):       # the built-in fallback equals field.hive_tag_corners
        a = tagkit.up_cell_tag_corners("red", which)
        b = tagkit._fallback_up_cell_tag_corners("red", which)
        assert all(np.allclose(a[k], b[k], atol=1e-6) for k in a)
    d = tagkit.hive_tag_defs("red", learned={45: np.zeros((4, 3)), 34: np.ones((4, 3))})
    assert sorted(d) == [34, 35, 36, 37, 45]
    assert np.allclose(d[34], tags[34])         # computed wins over learned
    assert sorted(tagkit.combined_tag_defs("red")) == [34, 35, 36, 37, 100, 101, 102, 103]


@pytest.mark.parametrize("option", ["gopro", "usb"])
def test_computed_up_tags_at_recommended_poses(option):
    from hiveshot import field

    cams = {k: _vcam(option, k) for k in "AB"}
    up = tagkit.up_cell_tag_corners("red", "audience")
    imgs = {k: render_tag_dict(cams[k], up, seed=3) for k in "AB"}
    kit = tagkit.tag_defs()
    for k, cam in cams.items():
        assert sorted(d["id"] for d in calib.detect_apriltags(imgs[k])) == [34, 35, 36, 37]
        # HIVE tags alone (small cluster): coarse pose only
        ext, info = calib.solve_extrinsics_from_tags(cam.intr, imgs[k],
                                                     tagkit.hive_tag_defs("red"), cam.cam_id)
        assert np.linalg.norm(_pos(ext) - _pos(cam.extr)) < 2.5, (option, k)
        assert _rot_deg(ext, cam.extr) < 2.0, (option, k)
        # mixed kit + HIVE tags in one image: accurate
        both = render_tag_dict(cam, {**{i: c for i, c in kit.items()}, **up}, seed=4)
        ext, info = calib.solve_extrinsics_from_tags(cam.intr, both,
                                                     tagkit.combined_tag_defs("red"), cam.cam_id)
        assert info["tags_used"] == [34, 35, 36, 37, 100, 101, 102, 103]
        assert np.linalg.norm(_pos(ext) - _pos(cam.extr)) < 0.5
        assert _rot_deg(ext, cam.extr) < 0.3
    # learning at the recommended poses reproduces the computed geometry (verification)
    learned, linfo = tagkit.learn_hive_tags(cams["A"].intr, cams["A"].extr, imgs["A"],
                                            cams["B"].intr, cams["B"].extr, imgs["B"],
                                            alliance="red", state=field.HiveState("red", "audience"))
    assert linfo["ids_learned"] == [34, 35, 36, 37]
    assert max(linfo["error_vs_computed_in"].values()) < 0.5
    # roll rule: right-side-up cluster at 49.9 in -> red audience CELL is up
    cp = {c.cam_id: (c.intr, c.extr) for c in cams.values()}
    dets = {c.cam_id: calib.detect_apriltags(imgs[k]) for k, c in cams.items()}
    info = tagkit.up_cells_from_tags(dets, cp)
    assert info["up"]["red"] == "audience" and info["confidence"] == 1.0
    assert info["clusters"]["red_audience"]["height_in"] == pytest.approx(49.9, abs=0.5)
    assert tagkit.infer_hive_state(None, dets, cp) == ("red/audience", 1.0)
    assert tagkit.infer_hive_state(None, dets, None) == (None, 0.0)


def test_upside_down_cluster_is_not_up():
    """Tags seen rolled 180 deg (z of the tag's up vector < 0) never mark the cell as up."""
    cam = _vcam("gopro", "B")
    cp = {"cam1": (cam.intr, cam.extr)}
    up = tagkit.up_cell_tag_corners("red", "audience")
    for flip, expect_up in ((False, True), (True, False)):
        dets = []
        for tid, c in up.items():
            cc = c[[2, 3, 0, 1]] if flip else c
            u, v = cam.project(cc)
            dets.append({"id": tid, "corners": np.c_[u, v]})
        v = tagkit.tag_up_vector_field(dets[0]["corners"], cam.intr, cam.extr)
        assert (v[2] > 0) == expect_up
        res = tagkit.up_cells_from_tags({"cam1": dets}, cp)
        assert (res["up"]["red"] == "audience") == expect_up

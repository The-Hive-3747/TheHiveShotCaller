from __future__ import annotations

import cv2
import numpy as np
import pytest

from hiveshot import calib, calib_targets
from hiveshot.models import CameraExtrinsics, CameraIntrinsics

W, H = 1920, 1080


def make_intr(cam_id="a"):
    return CameraIntrinsics(cam_id, W, H, 1400.0, 1400.0, 960.0, 540.0, (-0.05, 0.01, 0.0, 0.0, 0.0))


def look_at_ext(cam_id, cam_pos, target):
    """Extrinsics for a camera at cam_pos looking at target (Z up in field)."""
    cam_pos, target = np.asarray(cam_pos, float), np.asarray(target, float)
    zc = target - cam_pos
    zc /= np.linalg.norm(zc)
    xc = np.cross(zc, [0, 0, 1.0])
    xc /= np.linalg.norm(xc)
    yc = np.cross(zc, xc)
    R = np.vstack([xc, yc, zc])
    t = -R @ cam_pos
    rvec, _ = cv2.Rodrigues(R)
    return CameraExtrinsics(cam_id, tuple(rvec.reshape(3)), tuple(t))


def test_intrinsics_from_corners():
    rng = np.random.default_rng(1)
    intr = make_intr()
    objp = calib.checkerboard_object_points((9, 6), 1.0)
    K, D = calib.camera_matrix(intr), calib.dist_coeffs(intr)
    objs, imgs = [], []
    while len(objs) < 12:
        rvec = rng.uniform(-0.5, 0.5, 3)
        tvec = np.array([-4 + rng.uniform(-3, 3), -2.5 + rng.uniform(-2, 2), rng.uniform(20, 40)])
        uv, _ = cv2.projectPoints(objp.reshape(-1, 1, 3), rvec, tvec, K, D)
        uv = uv.reshape(-1, 2)
        if uv[:, 0].min() < 0 or uv[:, 0].max() > W or uv[:, 1].min() < 0 or uv[:, 1].max() > H:
            continue
        objs.append(objp)
        imgs.append(uv + rng.normal(0, 0.2, uv.shape))
    out = calib.calibrate_intrinsics_from_corners(objs, imgs, (W, H), "a")
    assert abs(out.fx - 1400) / 1400 < 0.01
    assert out.reprojection_rmse_px < 0.5


def test_too_few_frames_raises():
    blank = np.full((720, 1280, 3), 255, np.uint8)
    try:
        calib.calibrate_intrinsics([blank] * 3, cam_id="a")
    except ValueError as e:
        assert "at least 8" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_extrinsics_recovered():
    rng = np.random.default_rng(2)
    intr = make_intr()
    ext = look_at_ext("a", [150, -120, 90], [0, 0, 30])
    fld = np.array(
        [[-48, -48, 0], [48, 48, 0], [-12, 8, 55], [12, 8, 55],
         [-12, -8, 60], [12, -8, 50], [-25, 19, 0], [25, -19, 0]], float)
    uv = calib.project(intr, ext, fld) + rng.normal(0, 0.2, (8, 2))
    sol = calib.solve_extrinsics_from_points(intr, uv, fld, "a")
    Ra, _ = cv2.Rodrigues(np.array(ext.rvec))
    Rb, _ = cv2.Rodrigues(np.array(sol.rvec))
    ang = np.degrees(np.arccos(np.clip((np.trace(Ra.T @ Rb) - 1) / 2, -1, 1)))
    cam_a = -Ra.T @ np.array(ext.tvec)
    cam_b = -Rb.T @ np.array(sol.tvec)
    assert ang < 0.2
    assert np.linalg.norm(cam_a - cam_b) < 0.5
    assert sol.rmse_in < 0.5
    rep = calib.reprojection_report(intr, sol, uv, fld)
    assert len(rep["per_point_px"]) == 8 and rep["rmse_px"] < 1.0


def test_triangulate_two_cameras():
    rng = np.random.default_rng(3)
    ia, ib = make_intr("a"), make_intr("b")
    ea = look_at_ext("a", [200, 0, 60], [0, 0, 50])
    eb = look_at_ext("b", [0, 200, 60], [0, 0, 50])
    xyz = rng.uniform([-20, -20, 40], [20, 20, 80], (50, 3))
    ua = calib.project(ia, ea, xyz) + rng.normal(0, 0.3, (50, 2))
    ub = calib.project(ib, eb, xyz) + rng.normal(0, 0.3, (50, 2))
    est, res = calib.triangulate(ia, ea, ua, ib, eb, ub)
    err = np.linalg.norm(est - xyz, axis=1)
    assert err.max() < 0.5
    assert res.shape == (50,) and np.all(res > 0) and res.max() < 1.0
    # Noise-free: residual ~ 0.
    est0, res0 = calib.triangulate(ia, ea, calib.project(ia, ea, xyz), ib, eb, calib.project(ib, eb, xyz))
    assert np.abs(est0 - xyz).max() < 0.01 and res0.max() < 0.01


def test_save_load_roundtrip(tmp_path):
    ia = make_intr("a")
    ea = look_at_ext("a", [200, 0, 60], [0, 0, 50])
    ea.rmse_in = 0.25
    p = tmp_path / "sub" / "cal.json"
    calib.save_calibration(p, [ia], [ea])
    i2, e2 = calib.load_calibration(p)
    assert i2 == [ia] and e2 == [ea]


def test_apriltag_placeholder_ids():
    tags = calib.default_hive_tag_corners()
    assert len(tags) == 16 and all(v.shape == (4, 3) for v in tags.values())


def test_checkerboard_pdf_and_png(tmp_path):
    pdf = tmp_path / "board.pdf"
    png = calib_targets.write_checkerboard_pdf(pdf)
    assert pdf.read_bytes().startswith(b"%PDF")
    assert pdf.read_bytes().rstrip().endswith(b"%%EOF")
    img = cv2.imread(str(png), cv2.IMREAD_GRAYSCALE)
    # Find the board's top row: a row through the middle of the first square row.
    dark_rows = np.where((img < 128).sum(axis=1) > 100)[0]
    row = img[dark_rows.min() + 150]  # ~half a square (300 px) below top edge of the board
    dark = row < 128
    runs = int(dark[0]) + int(np.count_nonzero(dark[1:] & ~dark[:-1]))
    assert runs == 5  # 10 squares alternating B W B W ... -> 5 black squares
    transitions = np.count_nonzero(dark[1:] != dark[:-1])
    assert transitions == 10


def test_field_point_sheet(tmp_path):
    p = calib_targets.write_field_point_sheet(tmp_path / "pts.md")
    text = p.read_text(encoding="utf-8")
    assert "VERIFY" in text and text.count("\n| ") >= 8


def test_real_corner_detection_on_warped_board(tmp_path):
    img, _ = calib_targets.render_checkerboard()
    dark_rows = np.where((img < 128).sum(axis=1) > 100)[0]
    dark_cols = np.where((img < 128).sum(axis=0) > 100)[0]
    crop = img[dark_rows.min() - 60: dark_rows.min() + 2100 + 60, dark_cols.min() - 60: dark_cols.min() + 3000 + 60]
    h, w = crop.shape
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[300, 150], [1000, 180], [980, 560], [330, 520]])
    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(crop, M, (1280, 720), borderValue=255)
    ok, corners = cv2.findChessboardCorners(warped, (9, 6))
    assert ok and len(corners) == 54


# ---------------------------------------------------------------- reference points (DoD 9)
def test_cell_reference_points_equal_field_polygon():
    """Every reference point that claims to be a CELL corner is a corner of the polygon in
    hiveshot.field (single source of truth), including the 8.8 in y offset the old,
    independently derived sheet had."""
    from hiveshot import field

    st = field.HiveState("red", "audience")
    poly = field.cell_opening_polygon("red", "audience", st)
    pts = dict(calib_targets.field_reference_points())
    cell = {n: p for n, p in pts.items() if "up-CELL opening" in n}
    assert len(cell) == 4
    for name, p in cell.items():
        d = np.linalg.norm(poly - np.asarray(p), axis=1)
        assert d.min() < 1e-6, f"{name} {p} is not a field.py CELL corner (min dist {d.min()})"
    # all four polygon corners are covered exactly once
    used = {int(np.argmin(np.linalg.norm(poly - np.asarray(p), axis=1))) for p in cell.values()}
    assert used == {0, 1, 2, 3}
    centre = np.mean(list(cell.values()), axis=0)
    c_field, _ = field.cell_opening_plane("red", "audience", st)
    assert np.allclose(centre, c_field, atol=1e-6)
    assert centre[1] == pytest.approx(field.OPENING_CENTER_ABS_Y)
    # named corners: left = -X, high = larger z
    assert cell["Red HIVE up-CELL opening, high-left corner"][0] < cell[
        "Red HIVE up-CELL opening, high-right corner"][0]
    assert cell["Red HIVE up-CELL opening, high-left corner"][2] > cell[
        "Red HIVE up-CELL opening, low-left corner"][2]


def test_frame_reference_points_are_wireframe_corners():
    from hiveshot import field

    segs = field.hive_frame_wireframe()
    ends = [np.asarray(e) for s in segs for e in s]
    pts = calib_targets.field_reference_points()
    assert len(pts) == 8
    for n, p in pts[4:]:
        assert "frame top corner" in n
        assert min(np.linalg.norm(e - np.asarray(p)) for e in ends) < 1e-9
    # both audience-side (+Y) and far-side (-Y), both +-X
    assert {(np.sign(p[0]), np.sign(p[1])) for _, p in pts[4:]} == {(-1, 1), (1, 1), (-1, -1),
                                                                    (1, -1)}
    # audience-side top bar is a horizontal wireframe segment between the first two
    a, b = np.asarray(pts[4][1]), np.asarray(pts[5][1])
    assert any((np.allclose(s[0], a) and np.allclose(s[1], b))
               or (np.allclose(s[0], b) and np.allclose(s[1], a)) for s in segs)


def test_reference_point_names_helper():
    names = calib_targets.reference_point_names()
    pts = calib_targets.field_reference_points()
    assert names == [n for n, _ in pts] and len(set(names)) == 8
    assert names[0] == "Red HIVE up-CELL opening, high-left corner"


def test_point_sheet_axes_match_field_py(tmp_path):
    text = calib_targets.write_field_point_sheet(tmp_path / "pts.md").read_text(encoding="utf-8")
    assert "+Y toward the audience" in text
    assert "X toward the audience" not in text.replace("+Y toward the audience", "")
    for _, (x, y, z) in calib_targets.field_reference_points():
        assert f"{x:.2f} | {y:.2f} | {z:.2f}" in text

import math

import numpy as np
import pytest

from hiveshot import field
from hiveshot import field_constants as C

ST = field.HiveState("red", "audience")


def test_center_on_plane_and_z_exact():
    for al in ("red", "blue"):
        for which in ("audience", "far"):
            poly = field.cell_opening_polygon(al, which, ST)
            pt, n = field.cell_opening_plane(al, which, ST)
            assert np.allclose(poly.mean(axis=0), pt)
            assert np.allclose((poly - pt) @ n, 0, atol=1e-9)
    pt, _ = field.cell_opening_plane("red", "audience", ST)
    assert pt[2] == pytest.approx(C.UP_CELL_OPENING_CENTER_Z)
    assert pt[0] == pytest.approx(C.RED_HIVE_X)
    pt, _ = field.cell_opening_plane("red", "far", ST)
    assert pt[1] < 0 and pt[2] < C.UP_CELL_OPENING_CENTER_Z
    poly = field.cell_opening_polygon("red", "audience", ST)
    assert poly[:, 2].min() == pytest.approx(C.UP_CELL_OPENING_BOTTOM_Z, abs=0.05)
    assert poly[:, 2].max() == pytest.approx(C.UP_CELL_OPENING_TOP_Z, abs=0.05)


def test_normal_unit_points_away_from_pivot_and_angle():
    pt, n = field.cell_opening_plane("blue", "audience", ST)
    assert np.linalg.norm(n) == pytest.approx(1.0)
    pivot = np.array([C.BLUE_HIVE_X, 0, C.PIVOT_HEIGHT])
    assert np.dot(pt - pivot, n) > 0
    elev = math.degrees(math.asin(n[2]))
    assert elev == pytest.approx(30.0, abs=0.2)  # CAD: exactly the 30 deg beam tilt
    assert n[1] > 0
    _, nf = field.cell_opening_plane("blue", "far", ST)
    assert nf[1] < 0


def test_polygon_width_height():
    poly = field.cell_opening_polygon("red", "audience", ST)
    assert len(poly) == 4
    assert np.ptp(poly[:, 0]) == pytest.approx(20.0)
    assert np.linalg.norm(poly[2] - poly[1]) == pytest.approx(14.0)
    g = field.cell_opening_polygon("red", "audience", ST, gabled=True)
    assert len(g) == 5
    assert np.ptp(g[:, 0]) == pytest.approx(20.0)


def test_swapped_state_swaps_heights():
    st = field.HiveState("red", "far")
    pt, _ = field.cell_opening_plane("red", "far", st)
    assert pt[2] == pytest.approx(C.UP_CELL_OPENING_CENTER_Z)
    pt, _ = field.cell_opening_plane("red", "audience", st)
    assert pt[2] < C.UP_CELL_OPENING_CENTER_Z
    far_up = field.cell_opening_plane("red", "far", st)[0]
    aud_up = field.cell_opening_plane("red", "audience", ST)[0]
    assert far_up[1] == pytest.approx(-aud_up[1]) and far_up[2] == pytest.approx(aud_up[2])


def test_segment_crossing():
    c, n = field.cell_opening_plane("red", "audience", ST)
    r = field.segment_crosses_opening(c + 10 * n, c - 10 * n, "red", "audience", ST)
    assert r is not None
    t, p = r
    assert t == pytest.approx(0.5)
    assert np.allclose(p, c)
    # outward (wrong direction) does not count
    assert field.segment_crosses_opening(c - 10 * n, c + 10 * n, "red", "audience", ST) is None
    # 30 in to the side
    side = np.array([30.0, 0, 0])
    assert field.segment_crosses_opening(c + side + 10 * n, c + side - 10 * n,
                                         "red", "audience", ST) is None
    # short segment that stops before the plane
    assert field.segment_crosses_opening(c + 10 * n, c + 1 * n, "red", "audience", ST) is None


def test_ball_radius_inset():
    c, n = field.cell_opening_plane("red", "audience", ST)
    off = np.array([9.0, 0, 0])
    a, b = c + off + 5 * n, c + off - 5 * n
    assert field.segment_crosses_opening(a, b, "red", "audience", ST, 0.0)
    off = np.array([8.0, 0, 0])
    a, b = c + off + 5 * n, c + off - 5 * n
    assert field.segment_crosses_opening(a, b, "red", "audience", ST, 1.4)
    off = np.array([9.0, 0, 0])
    a, b = c + off + 5 * n, c + off - 5 * n
    assert field.segment_crosses_opening(a, b, "red", "audience", ST, 1.4) is None


def test_point_inside_cell():
    c, n = field.cell_opening_plane("red", "audience", ST)
    assert field.point_inside_cell(c - 5 * n, "red", "audience", ST)
    assert not field.point_inside_cell(c + 1 * n, "red", "audience", ST)
    assert not field.point_inside_cell(c - (C.CELL_EXTENT_Y + 1) * n, "red", "audience", ST)
    assert not field.point_inside_cell(c - 5 * n + np.array([11.0, 0, 0]), "red", "audience", ST)


def test_wireframe_bounds_json():
    segs = field.hive_frame_wireframe()
    assert all(len(s) == 2 and len(s[0]) == 3 for s in segs)
    lo, hi = field.field_bounds()
    assert lo[0] == -72 and hi[1] == 72
    j = field.to_json()
    assert set(j["hives"]) == {"red", "blue"}
    assert len(j["wireframe"]) == len(segs)
    import json
    json.dumps(j)
    with pytest.raises(ValueError):
        field.HiveState("green", "far")


# ---- CELL floor / HIVE AprilTags / rigid-body down CELL
def test_cell_floor_frame():
    o, ux, ud, nrm = field.cell_floor_frame("red", "audience", ST)
    c, n = field.cell_opening_plane("red", "audience", ST)
    poly = field.cell_opening_polygon("red", "audience", ST)
    assert np.allclose(o, (poly[0] + poly[1]) / 2)           # bottom-edge center
    assert np.allclose(ux, [1, 0, 0])
    assert np.allclose(ud, -n)
    assert np.dot(nrm, ud) == pytest.approx(0, abs=1e-12) and nrm[2] < 0
    assert np.allclose(nrm, [0, 0.5, -0.866], atol=1e-3)


def test_tag_ids_and_size():
    t = field.hive_tag_corners("red", "audience", ST)
    assert list(t) == [34, 35, 36, 37]
    assert list(field.hive_tag_corners("red", "far", ST)) == [30, 31, 32, 33]
    assert list(field.hive_tag_corners("blue", "audience", ST)) == [38, 39, 40, 41]
    assert list(field.hive_tag_corners("blue", "far", ST)) == [42, 43, 44, 45]
    for cor in t.values():
        assert cor.shape == (4, 3)
        sides = [np.linalg.norm(cor[(i + 1) % 4] - cor[i]) for i in range(4)]
        assert sides == pytest.approx([C.APRILTAG_SIZE] * 4)
        assert np.dot(cor[1] - cor[0], cor[3] - cor[0]) == pytest.approx(0, abs=1e-9)


def test_tag_row_center_and_normal():
    # Expected from the official CAD (evidence/m1_field/step_extract.md): sticker center
    # (y_up 49.666, z_audience 12.887) + 0.25 in toward the opening along the beam.
    t = field.hive_tag_corners("red", "audience", ST)
    centers = np.array([c.mean(axis=0) for c in t.values()])
    row = centers.mean(axis=0)
    assert row[0] == pytest.approx(C.RED_HIVE_X, abs=0.1)
    assert (row[1], row[2]) == pytest.approx(C.HIVE_TAG_ROW_CENTER_UP, abs=0.1)
    assert (row[1], row[2]) == pytest.approx((13.10, 49.79), abs=0.1)  # CAD sticker center + 0.25
    # centers spaced +-2.75 / +-6.5 from the row center along one line
    assert sorted(np.abs(centers[:, 0] - row[0])) == pytest.approx([2.75, 2.75, 6.5, 6.5])
    assert np.allclose(centers[:, 1:], row[1:], atol=1e-9)
    for cor in t.values():
        nrm = np.cross(cor[1] - cor[0], cor[3] - cor[0])
        nrm /= np.linalg.norm(nrm)
        # aruco order seen from outside: TL->TR x TL->BL points INTO the scene, so the face
        # normal toward the viewer is -nrm
        face = -nrm
        ang = math.degrees(math.acos(np.clip(np.dot(face, [0, 0.5, -0.866]), -1, 1)))
        assert ang < 1.0


def test_tag_orientation_bottom_edge_toward_pivot():
    t = field.hive_tag_corners("red", "audience", ST)
    pivot = np.array([C.RED_HIVE_X, 0, C.PIVOT_HEIGHT])
    for cor in t.values():
        top = (cor[0] + cor[1]) / 2
        bot = (cor[2] + cor[3]) / 2
        assert np.linalg.norm(bot - pivot) < np.linalg.norm(top - pivot)
    # far-up state mirrors: tags of the far CELL face the far side and down
    st = field.HiveState("red", "far")
    for cor in field.hive_tag_corners("red", "far", st).values():
        face = -np.cross(cor[1] - cor[0], cor[3] - cor[0])
        face /= np.linalg.norm(face)
        assert face == pytest.approx([0, -0.5, -0.866], abs=2e-2)


def test_down_cell_rigid_body_matches_cad_tag():
    # CAD: the far (scoring) sticker is the audience sticker with a -> -a: center
    # (y_up 35.647, z_aud -11.394) in CAD = field y -11.394, z 35.647, row +0.25 toward opening.
    t = field.hive_tag_corners("red", "far", ST)
    row = np.array([c.mean(axis=0) for c in t.values()]).mean(axis=0)
    assert row[1] == pytest.approx(-11.394 - 0.25 * math.cos(math.radians(30)) , abs=0.1)
    assert row[2] == pytest.approx(35.647 - 0.25 * math.sin(math.radians(30)), abs=0.1)


def test_hive_lowest_point_matches_official():
    z = field.hive_lowest_point_z(ST)
    assert z == pytest.approx(C.HIVE_LOWEST_POINT_Z, abs=1.5)   # official Figure 9-9: 30.6
    assert field.hive_lowest_point_z(field.HiveState("red", "far")) == pytest.approx(z)


def test_red_at_plus_x_and_tag_ids_ascend_toward_minus_x():
    assert C.RED_HIVE_X > 0 > C.BLUE_HIVE_X
    for al, sign in (("red", 1), ("blue", -1)):
        pt, _ = field.cell_opening_plane(al, "audience", ST)
        assert np.sign(pt[0]) == sign
        t = field.hive_tag_corners(al, "audience", ST)
        xs = [t[i].mean(axis=0)[0] for i in sorted(t)]
        assert xs == sorted(xs, reverse=True)           # ids ascend toward -X
        assert np.mean(xs) == pytest.approx(sign * 12.75, abs=1e-6)
        # image-right of the tag (TL->TR) points toward -X for the audience-up CELL
        c = t[sorted(t)[0]]
        assert (c[1] - c[0])[0] < 0
    # far-up CELL is the mirror about the Y=0 plane
    st = field.HiveState("red", "far")
    tf = field.hive_tag_corners("red", "far", st)
    xs = [tf[i].mean(axis=0)[0] for i in sorted(tf)]
    assert xs == sorted(xs)                              # ids ascend toward +X


def test_constants_are_the_single_source():
    assert field.BEAM_A_OPEN == C.CELL_OPENING_ALONG_BEAM
    assert field.RIB_BOTTOM_RIM == C.GOAL_RIB_RIM_BELOW_OPENING
    pt, _ = field.cell_opening_plane("red", "audience", ST)
    assert pt[1] == pytest.approx(C.UP_CELL_OPENING_CENTER_Y, abs=0.01)
    far = field.cell_opening_plane("red", "far", ST)[0]
    assert far[2] == pytest.approx(C.DOWN_CELL_OPENING_CENTER_Z, abs=0.01)
    lo = field.cell_opening_polygon("red", "far", ST)[:, 2]
    assert (lo.min(), lo.max()) == pytest.approx(C.DOWN_CELL_OPENING_Z_RANGE, abs=0.05)


# ---- CAD frame (values typed from evidence/m1_field/step_extract.md, not from field_constants)
def _frame_pts(segs):
    return np.array([p for s in segs for p in s])


def test_frame_wireframe_matches_cad_vertices():
    segs = field.hive_frame_wireframe()
    pts = _frame_pts(segs)

    def has(p, tol=0.1):
        return np.min(np.linalg.norm(pts - np.array(p), axis=1)) <= tol

    for sx in (-1, 1):
        for sy in (-1, 1):
            assert has((sx * 24.73, sy * 19.47, 0.0))               # foot bar outer corners
            assert has((sx * 22.75, sy * 19.47, 0.0))               # foot bar inner corners
            assert has((sx * 12.60, sy * 0.52, 41.05))              # leg tops (apex end)
            assert has((sx * 23.81, sy * 18.56, 0.53))              # leg feet
        assert has((sx * 12.0, 0.0, 41.45))                         # crossbar ends
        assert has((sx * 12.0, 0.0, 44.27)) and has((sx * 11.15, 0.0, 41.57))  # pivot cradle
        assert has((sx * 15.07, 4.28, 34.07)) and has((sx * 15.07, -4.28, 40.02))  # logo panel
    # crossbar is a segment from -12 to +12 in X at 41.45
    assert any(np.allclose(sorted([a[0], b[0]]), [-12.0, 12.0], atol=0.1)
               and abs(a[2] - 41.45) < 0.1 and abs(b[2] - 41.45) < 0.1
               and abs(a[1]) < 0.1 and abs(b[1]) < 0.1 for a, b in segs)
    # no leftover box "top corners": nothing but the CELLs rises above the pivot cradle (44.3)
    # outside the openings; and nothing at the old 63.95 / (+-24.73, +-19.475) location
    assert not has((24.73, 19.475, 63.95), tol=1.0)
    assert not hasattr(field, "FRAME_TOP_Z")


def test_frame_reference_points_are_cad_features():
    refs = dict(field.frame_reference_points())
    assert len(refs) == 7
    assert np.allclose(refs["Frame crossbar end (+X apex)"], [12.0, 0, 41.45], atol=0.1)
    assert np.allclose(refs["Frame crossbar end (-X apex)"], [-12.0, 0, 41.45], atol=0.1)
    assert np.allclose(refs["Frame crossbar midpoint"], [0, 0, 41.45], atol=0.1)
    corners = {n: p for n, p in refs.items() if "base corner" in n}
    assert len(corners) == 4
    for p in corners.values():
        assert abs(abs(p[0]) - 24.73) <= 0.1 and abs(abs(p[1]) - 19.47) <= 0.1 and p[2] == 0.0
    segs = field.hive_frame_wireframe()
    pts = _frame_pts(segs)
    for p in refs.values():  # every reference is on the drawn frame
        assert np.min(np.linalg.norm(pts - p, axis=1)) < 1e-6 or abs(p[0]) < 1e-9


def test_frame_to_json_and_perimeter():
    j = field.to_json()
    assert len(j["wireframe"]) == len(field.hive_frame_wireframe())
    assert len(j["frame_reference_points"]) == 7
    top = max(max(a[2], b[2]) for a, b in j["wireframe"])
    assert top < 66.0                                  # CELLs only; the frame peaks at 44.3
    assert C.FIELD_INSIDE_SIZE_CAD == pytest.approx(141.35, abs=0.05)   # CAD glass inner faces
    assert C.FIELD_SIZE == 144.0                       # manual nominal kept
    assert j["field_inside_size_cad"] == C.FIELD_INSIDE_SIZE_CAD

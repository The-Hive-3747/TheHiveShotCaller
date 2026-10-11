"""Field and HIVE geometry in the field frame (inches).

Frame: origin at field center on the tile surface, Z up, X across the HIVE pair,
Y along the beams. CHOICE (documented): the "audience" CELL is the one at +Y and
the "far" CELL is the one at -Y.

RIGID-BODY MODEL (replaces the earlier fan-site numbers; validated against the
official field CAD, see evidence/m1_field/step_extract.md):
* Each HIVE beam is a rigid body pivoting about (hive_x, 0, PIVOT_HEIGHT),
  tilted +-CELL_TILT_DEG (30) about X. Beam coordinates: a along the beam
  (outward from the pivot), b perpendicular in the YZ plane (b_hat has z>0).
* Both CELLs sit at |a| = CELL_OPENING_ALONG_BEAM = 21.455 (opening plane, normal along
  the beam) and are offset +B_CENTER along b_hat from the axis. B_CENTER is
  chosen so the up opening center lands EXACTLY on UP_CELL_OPENING_CENTER_Z
  (59.55); its bottom/top edges then land at 53.49/65.61 (official 53.5/65.6).
  The far CELL is the near CELL rotated 180 deg about b_hat through the pivot
  (a -> -a, b unchanged), as in the CAD; its floor therefore also faces down.
* The opening plane is exactly perpendicular to the beam (30.0 deg); the 59.87 /
  30.13 deg constants are rounding of 12.1/14 and are not used.
* Up opening center (audience-up): y = 15.77, z = 59.55 (the old y = 24.25 came
  from an unofficial heuristic and disagreed with the CAD by ~8.5 in).
  Down opening center is derived by the rigid body (z = 38.09), not the fan value.
* Opening 20 in wide (X) by 14 in tall (in-plane). `gabled=True` gives the
  pentagon: full width up to the 7.61 in shoulder, peak at the full 14 in.
* hive_lowest_point_z: lowest rim of the down CELL, CAD-derived rim thickness
  GOAL_RIB_RIM_BELOW_OPENING below the opening bottom edge; comes out 30.61 vs official 30.6.
* Tag geometry (cell_floor_frame, hive_tag_corners): see those functions.
  Handedness: the CAD is right-handed with the red HIVE at CAD -X and the audience
  at CAD +Z; with the audience at +Y that puts red at +X, which is what
  field_constants now has (RED_HIVE_X = +12.75).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from . import field_constants as C

ALLIANCES = ("red", "blue")
CELLS = ("audience", "far")

_TILT = math.radians(C.CELL_TILT_DEG)
_S, _C = math.sin(_TILT), math.cos(_TILT)
BEAM_A_OPEN = C.CELL_OPENING_ALONG_BEAM                    # opening plane, along the beam (CAD)
B_CENTER = (C.UP_CELL_OPENING_CENTER_Z - C.PIVOT_HEIGHT - BEAM_A_OPEN * _S) / _C
HALF_H = C.CELL_OPENING_HEIGHT / 2.0
B_BOTTOM = B_CENTER - HALF_H                               # opening bottom edge, along b_hat
RIB_BOTTOM_RIM = C.GOAL_RIB_RIM_BELOW_OPENING
TAG_STICKER_BELOW_FLOOR = 0.12  # CAD: sticker plane sits 0.12 in outside the opening-bottom line
# y of the up CELL opening center (|y| of the up CELL in any state), from the rigid body;
# must agree with the CAD-recorded constant
OPENING_CENTER_ABS_Y = BEAM_A_OPEN * _C - B_CENTER * _S
assert abs(OPENING_CENTER_ABS_Y - C.UP_CELL_OPENING_CENTER_Y) < 0.01
FIELD_MAX_Z = 120.0  # assumed ceiling for bounds/viewer


@dataclass
class HiveState:
    alliance: str = "red"
    up_cell: str = "audience"

    def __post_init__(self) -> None:
        if self.alliance not in ALLIANCES:
            raise ValueError(f"alliance must be one of {ALLIANCES}")
        if self.up_cell not in CELLS:
            raise ValueError(f"up_cell must be one of {CELLS}")


def hive_x(alliance: str) -> float:
    if alliance == "red":
        return C.RED_HIVE_X
    if alliance == "blue":
        return C.BLUE_HIVE_X
    raise ValueError(alliance)


def _beam(which: str, state: HiveState):
    """Unit vectors (a_hat outward from the pivot toward CELL `which`, b_hat) for the
    beam in `state`."""
    if which not in CELLS:
        raise ValueError(which)
    tau = 1.0 if state.up_cell == "audience" else -1.0
    sigma = 1.0 if which == "audience" else -1.0
    a_aud = np.array([0.0, _C, tau * _S])
    a_hat = sigma * a_aud
    b_hat = np.array([0.0, -tau * _S, _C])
    return a_hat, b_hat


def _frame(alliance: str, which: str, state: HiveState):
    """Return (center, normal, in_plane_up) for a CELL opening."""
    a_hat, b_hat = _beam(which, state)
    pivot = np.array([hive_x(alliance), 0.0, C.PIVOT_HEIGHT])
    center = pivot + BEAM_A_OPEN * a_hat + B_CENTER * b_hat
    return center, a_hat.copy(), b_hat.copy()


def cell_floor_frame(alliance: str, which: str, state: HiveState):
    """CELL floor (Hive Bottom Skin exterior) frame: (origin, u_x, u_depth, normal).
    origin = center of the opening bottom edge; u_x = +X; u_depth runs from the
    opening into the cup (along -opening normal, toward the pivot); normal is the
    outward (exterior) face normal, facing down toward the tiles."""
    c, n, w = _frame(alliance, which, state)
    origin = c - HALF_H * w
    return origin, np.array([1.0, 0.0, 0.0]), -n, -w


def hive_tag_corners(alliance: str, which: str, state: HiveState) -> dict:
    """Corners (4,3) of the four 3.25 in AprilTags of this CELL cluster, keyed by id.
    Corner order is cv2.aruco: top-left, top-right, bottom-right, bottom-left as seen
    looking at the tag face with the sticker right-side up (sticker bottom edge toward
    the pivot, so image-up is toward the opening). The tag row center is
    TAG_ROW_FROM_CELL_FRONT behind the opening along u_depth and
    TAG_STICKER_BELOW_FLOOR outside the floor; ids ascend toward image-right (left to
    right on the sticker art, Figure 9-16) at offsets HIVE_TAG_ROW_OFFSETS_IN.
    Built right-handed from the face (image_right = normal x image_down): for the
    audience-up CELL, ids ascend toward -X in this frame (consistent with the CAD, where
    they ascend toward CAD +X and CAD X = -field X). VERIFY on the real field."""
    origin, _ux, udep, nrm = cell_floor_frame(alliance, which, state)
    ids = C.HIVE_TAG_CLUSTERS[f"{alliance}_{which}"]
    down = udep / np.linalg.norm(udep)
    right = np.cross(nrm, down)
    right /= np.linalg.norm(right)
    row = origin + C.TAG_ROW_FROM_CELL_FRONT * udep + TAG_STICKER_BELOW_FLOOR * nrm
    row[0] = hive_x(alliance)
    h = C.APRILTAG_SIZE / 2.0
    out = {}
    for tid, off in zip(ids, C.HIVE_TAG_ROW_OFFSETS_IN, strict=True):
        c = row + off * right
        out[tid] = np.array([c - h * right - h * down, c + h * right - h * down,
                             c + h * right + h * down, c - h * right + h * down])
    return out


def hive_lowest_point_z(state: HiveState) -> float:
    """Lowest point of either CELL (rim and cup extent) in `state`."""
    zs = []
    for which in CELLS:
        a_hat, b_hat = _beam(which, state)
        for da in (BEAM_A_OPEN, BEAM_A_OPEN - C.CELL_EXTENT_Y):
            for b in (B_BOTTOM - RIB_BOTTOM_RIM, B_BOTTOM + C.CELL_OPENING_HEIGHT):
                zs.append(C.PIVOT_HEIGHT + da * a_hat[2] + b * b_hat[2])
    return float(min(zs))


def _profile(gabled: bool) -> np.ndarray:
    """2D (a along X, b in-plane vertical) polygon about the opening center."""
    hw = C.CELL_OPENING_WIDTH / 2.0
    hh = C.CELL_OPENING_HEIGHT / 2.0
    if not gabled:
        return np.array([[-hw, -hh], [hw, -hh], [hw, hh], [-hw, hh]])
    sh = -hh + C.GABLE_SHOULDER_HEIGHT
    return np.array([[-hw, -hh], [hw, -hh], [hw, sh], [0.0, hh], [-hw, sh]])


def cell_opening_polygon(alliance: str, which_cell: str, state: HiveState,
                         gabled: bool = False) -> np.ndarray:
    c, _, w = _frame(alliance, which_cell, state)
    prof = _profile(gabled)
    return np.array([c + a * np.array([1.0, 0, 0]) + b * w for a, b in prof])


def cell_opening_plane(alliance: str, which: str, state: HiveState):
    c, n, _ = _frame(alliance, which, state)
    return c.copy(), n.copy()


def _inset_contains(prof: np.ndarray, a: float, b: float, r: float) -> bool:
    """Point inside convex CCW polygon, at least r from every edge."""
    k = len(prof)
    for i in range(k):
        p, q = prof[i], prof[(i + 1) % k]
        e = q - p
        L = math.hypot(e[0], e[1])
        # inward distance for CCW polygon
        d = (e[0] * (b - p[1]) - e[1] * (a - p[0])) / L
        if d < r:
            return False
    return True


def segment_crosses_opening(p0, p1, alliance: str, which: str, state: HiveState,
                            ball_radius: float = 0.0, gabled: bool = False
                            ) -> Optional[tuple[float, np.ndarray]]:
    """Inward crossing (against the outward normal) of the opening plane.
    Returns (t in [0,1], 3D point) if the crossing lies inside the opening
    polygon inset by ball_radius, else None."""
    p0 = np.asarray(p0, float)
    p1 = np.asarray(p1, float)
    c, n, w = _frame(alliance, which, state)
    d0 = float(np.dot(p0 - c, n))
    d1 = float(np.dot(p1 - c, n))
    if not (d0 > 0.0 >= d1):
        return None
    t = d0 / (d0 - d1)
    pt = p0 + t * (p1 - p0)
    rel = pt - c
    a = float(rel[0])
    b = float(np.dot(rel, w))
    if not _inset_contains(_profile(gabled), a, b, ball_radius):
        return None
    return t, pt


def point_inside_cell(p, alliance: str, which: str, state: HiveState,
                      gabled: bool = False) -> bool:
    """Inside the box behind the opening, CELL_EXTENT_Y deep along -normal."""
    p = np.asarray(p, float)
    c, n, w = _frame(alliance, which, state)
    rel = p - c
    depth = float(np.dot(rel, n))
    if not (-C.CELL_EXTENT_Y <= depth <= 0.0):
        return False
    return _inset_contains(_profile(gabled), float(rel[0]), float(np.dot(rel, w)), 0.0)


def _frame_segments():
    """CAD A-frame (see the 'Frame (CAD-extracted)' block in field_constants): per X end a foot
    bar on the tiles and two legs rising inward to the apex, a crossbar along X joining the
    apexes, pivot cradles on top, and the logo panel faces."""
    P = lambda *v: np.array(v, float)  # noqa: E731
    segs = []
    xo, xi, hy = C.FRAME_BASE_X_OUTER, C.FRAME_BASE_X_INNER, C.FRAME_BASE_HALF_Y
    lx, ly, lz = C.FRAME_LEG_TOP
    fx, fy, fz = C.FRAME_LEG_FOOT
    cz, ch = C.FRAME_CROSSBAR_Z, C.FRAME_CROSSBAR_HALF_X
    for sx in (-1, 1):
        # foot bar footprint on the tiles
        corners = [P(sx * xo, -hy, 0), P(sx * xo, hy, 0), P(sx * xi, hy, 0), P(sx * xi, -hy, 0)]
        segs += [(corners[i], corners[(i + 1) % 4]) for i in range(4)]
        for sy in (-1, 1):
            segs.append((P(sx * lx, sy * ly, lz), P(sx * fx, sy * fy, fz)))      # leg
            segs.append((P(sx * ch, 0.0, cz), P(sx * lx, sy * ly, lz)))          # crossbar end to leg top
        top, bot = C.FRAME_PIVOT_CRADLE
        segs.append((P(sx * top[0], 0.0, top[1]), P(sx * bot[0], 0.0, bot[1])))   # pivot cradle
    segs.append((P(-ch, 0.0, cz), P(ch, 0.0, cz)))                                # crossbar
    lp = C.FRAME_LOGO_PANEL
    for sy in (-1, 1):
        y = sy * lp["y_outer"]
        q = [P(-lp["half_x"], y, lp["z_lo"]), P(lp["half_x"], y, lp["z_lo"]),
             P(lp["half_x"], y, lp["z_hi"]), P(-lp["half_x"], y, lp["z_hi"])]
        segs += [(q[i], q[(i + 1) % 4]) for i in range(4)]
    return segs


def frame_reference_points():
    """Physically real, tape-measurable frame features: [(name, xyz)] for the two crossbar
    ends (apexes, bar centerline), the crossbar midpoint and the four outer base corners
    (foot bar outer corners on the tiles). Symmetric, so valid in either handedness."""
    ch, cz = C.FRAME_CROSSBAR_HALF_X, C.FRAME_CROSSBAR_Z
    pts = [("Frame crossbar end (+X apex)", np.array([ch, 0.0, cz])),
           ("Frame crossbar end (-X apex)", np.array([-ch, 0.0, cz])),
           ("Frame crossbar midpoint", np.array([0.0, 0.0, cz]))]
    for sx, nx in ((1, "+X"), (-1, "-X")):
        for sy, ny in ((1, "+Y"), (-1, "-Y")):
            pts.append((f"Frame base corner ({nx}, {ny})",
                        np.array([sx * C.FRAME_BASE_X_OUTER, sy * C.FRAME_BASE_HALF_Y, 0.0])))
    return pts


def hive_frame_wireframe(up_cells: Optional[dict] = None):
    """Segments (p0, p1): the CAD A-frame (base rails, four legs, crossbar, pivot cradles,
    logo panels), both beams and the CELL openings. up_cells maps alliance -> up_cell
    (default audience for both)."""
    up_cells = up_cells or {}
    segs = _frame_segments()
    for al in ALLIANCES:
        st = HiveState(al, up_cells.get(al, "audience"))
        a_hat, _ = _beam("audience", st)
        pivot = np.array([hive_x(al), 0.0, C.PIVOT_HEIGHT])
        segs.append((pivot - BEAM_A_OPEN * a_hat, pivot + BEAM_A_OPEN * a_hat))  # beam axis
        for which in CELLS:
            poly = cell_opening_polygon(al, which, st)
            for i in range(len(poly)):
                segs.append((poly[i], poly[(i + 1) % len(poly)]))
    return segs


def field_bounds(field_size_in: Optional[float] = None):
    """(min, max) corners of the field box; `field_size_in` (inside wall to inside wall, from
    the app config) overrides the nominal FIELD_SIZE."""
    h = (C.FIELD_SIZE if field_size_in is None else float(field_size_in)) / 2.0
    return np.array([-h, -h, 0.0]), np.array([h, h, FIELD_MAX_Z])


def to_json(up_cells: Optional[dict] = None, field_size_in: Optional[float] = None) -> dict:
    up_cells = up_cells or {}
    size = C.FIELD_SIZE if field_size_in is None else float(field_size_in)
    lo, hi = field_bounds(size)
    hives = {}
    for al in ALLIANCES:
        st = HiveState(al, up_cells.get(al, "audience"))
        cells = {}
        for which in CELLS:
            pt, n = cell_opening_plane(al, which, st)
            cells[which] = {
                "is_up": which == st.up_cell,
                "center": pt.tolist(),
                "normal": n.tolist(),
                "opening": cell_opening_polygon(al, which, st).tolist(),
                "opening_gabled": cell_opening_polygon(al, which, st, gabled=True).tolist(),
                "tags": {str(k): v.tolist() for k, v in hive_tag_corners(al, which, st).items()},
            }
        hives[al] = {"x": hive_x(al), "up_cell": st.up_cell,
                     "pivot": [hive_x(al), 0.0, C.PIVOT_HEIGHT], "cells": cells}
    return {
        "field_size": size,
        "bounds": {"min": lo.tolist(), "max": hi.tolist()},
        "hives": hives,
        "wireframe": [[a.tolist(), b.tolist()] for a, b in hive_frame_wireframe(up_cells)],
        "frame_reference_points": [{"name": n, "xyz": p.tolist()} for n, p in frame_reference_points()],
        "field_inside_size_cad": C.FIELD_INSIDE_SIZE_CAD,
        "cell_extent": C.CELL_EXTENT_Y,
    }

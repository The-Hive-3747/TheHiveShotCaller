"""Field and HIVE geometry in the field frame (inches).

Frame: origin at field center on the tile surface, Z up, X across the HIVE pair,
Y along the beams. CHOICE (documented): the "audience" CELL is the one at +Y and
the "far" CELL is the one at -Y.

RIGID-BODY MODEL (replaces the earlier fan-site numbers; validated against the
official field CAD, see evidence/m1_field/step_extract.md):
* Each HIVE beam is a rigid body pivoting about (hive_x, 0, PIVOT_HEIGHT),
  tilted +-CELL_TILT_DEG (30) about X. Beam coordinates: a along the beam
  (outward from the pivot), b perpendicular in the YZ plane (b_hat has z>0).
* Both CELLs sit at |a| = CELL_PAIR_SPAN/2 = 21.455 (opening plane, normal along
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
  RIB_BOTTOM_RIM below the opening bottom edge; comes out 30.61 vs official 30.6.
* Tag geometry (cell_floor_frame, hive_tag_corners): see those functions.
  Handedness note: the CAD is right-handed with the red HIVE at CAD -X and the
  audience at CAD +Z, which in a right-handed frame with audience at +Y puts red
  at +X. field_constants has RED_HIVE_X = -12.75, so red/blue X positions are
  mirrored relative to the real field (tag-face geometry here is built
  right-handed from the face itself and is unaffected).
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
BEAM_A_OPEN = C.CELL_PAIR_SPAN / 2.0                       # opening plane, along the beam
B_CENTER = (C.UP_CELL_OPENING_CENTER_Z - C.PIVOT_HEIGHT - BEAM_A_OPEN * _S) / _C
HALF_H = C.CELL_OPENING_HEIGHT / 2.0
B_BOTTOM = B_CENTER - HALF_H                               # opening bottom edge, along b_hat
RIB_BOTTOM_RIM = 1.64          # CAD: Goal Rib extends 1.64 in below the opening bottom edge
TAG_STICKER_BELOW_FLOOR = 0.12  # CAD: sticker plane sits 0.12 in outside the opening-bottom line
# y of the up CELL opening center in the audience-up state (|y| of the up CELL in any state)
OPENING_CENTER_ABS_Y = BEAM_A_OPEN * _C - B_CENTER * _S
FRAME_TOP_Z = C.PIVOT_HEIGHT + 20.0  # frame box height is not in constants; assumed
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
    VERIFY: the direction of ascending ids relative to +X. Built right-handed from the
    face (image_right = normal x image_down), so for the audience-up CELL ids ascend
    toward -X in this frame (the requested 'ids ascend toward +X' assumption does not
    hold for a right-handed frame; the CAD has them ascending toward its +X, where the
    red HIVE is at CAD -X)."""
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


def _box_edges(lo, hi):
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    v = [(x, y, z) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
    idx = [(0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7),
           (0, 4), (1, 5), (2, 6), (3, 7)]
    return [(np.array(v[i], float), np.array(v[j], float)) for i, j in idx]


def hive_frame_wireframe(up_cells: Optional[dict] = None):
    """Segments (p0, p1) for the frame box and both beams (and cell openings).
    up_cells maps alliance -> up_cell (default audience for both)."""
    up_cells = up_cells or {}
    segs = _box_edges((-C.FRAME_WIDTH_X / 2, -C.FRAME_DEPTH_Y / 2, 0.0),
                      (C.FRAME_WIDTH_X / 2, C.FRAME_DEPTH_Y / 2, FRAME_TOP_Z))
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


def field_bounds():
    h = C.FIELD_SIZE / 2.0
    return np.array([-h, -h, 0.0]), np.array([h, h, FIELD_MAX_Z])


def to_json(up_cells: Optional[dict] = None) -> dict:
    up_cells = up_cells or {}
    lo, hi = field_bounds()
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
        "field_size": C.FIELD_SIZE,
        "bounds": {"min": lo.tolist(), "max": hi.tolist()},
        "hives": hives,
        "wireframe": [[a.tolist(), b.tolist()] for a, b in hive_frame_wireframe(up_cells)],
        "cell_extent": C.CELL_EXTENT_Y,
    }

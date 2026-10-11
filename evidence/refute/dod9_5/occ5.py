"""DoD 9 round 5, attack 1: line of sight from the two documented camera spots to every kit tag
(black square grid incl. corners), the quiet-zone ring, the 8 click points and the HIVE tags 34-37,
in field.CALIBRATION_STATE (both audience CELLs up).
Occluders: (a) the project's own field.segment_hits_any_cell, (b) an independent convex-hull test of
field.cell_body_corners (scipy Delaunay, optionally dilated), (c) CAD frame parts (legs as capsules,
foot bars, crossbar, top corner blocks, axle holders, both logo panels as thin plates), (d) FLOWER
boxes/cylinders, (e) the perimeter wall slab (nominal 144 in field, outer face 1.5 in, 12 in high).
Camera placements: nominal and the 8 corners of +-1 in x, +-1 in y, +-0.5 in lens height.
Run: PYTHONPATH=. .venv/Scripts/python.exe evidence/refute/dod9_5/occ5.py
"""
import itertools
import json

import numpy as np
from scipy.spatial import ConvexHull, Delaunay

from hiveshot import calib_targets as ct
from hiveshot import field, tagkit
from hiveshot import field_constants as C
from hiveshot import placement as pl

ST = field.CALIBRATION_STATE
STEP = 0.05


def seg_samples(p0, p1, stop_short):
    d = p1 - p0
    L = np.linalg.norm(d)
    n = max(2, int((L - stop_short) / STEP))
    t = np.linspace(0.0, (L - stop_short) / L, n)
    return p0[None] + t[:, None] * d[None]


# ---------------------------------------------------------------- occluder predicates (points)
def box(p, lo, hi, pad=0.0):
    return np.all((p >= np.array(lo) - pad) & (p <= np.array(hi) + pad), axis=1)


def capsule(p, a, b, r):
    a, b = np.asarray(a, float), np.asarray(b, float)
    ab = b - a
    t = np.clip(((p - a) @ ab) / (ab @ ab), 0, 1)
    q = a + t[:, None] * ab
    return np.linalg.norm(p - q, axis=1) <= r


def frame_hits(p):
    """dict name -> bool array"""
    out = {}
    h = np.zeros(len(p), bool)
    for sx in (-1, 1):
        for sy in (-1, 1):
            h |= capsule(p, (sx * 12.6, sy * 0.52, 41.05), (sx * 23.81, sy * 18.56, 0.53), 0.6)
    out["legs"] = h
    h = np.zeros(len(p), bool)
    for sx in (-1, 1):
        lo, hi = sorted((sx * 22.75, sx * 24.73))
        h |= box(p, (lo, -19.47, 0), (hi, 19.47, 2.15))
    out["footbars"] = h
    out["crossbar"] = box(p, (-12, -0.5, 40.95), (12, 0.5, 41.95))
    h = np.zeros(len(p), bool)
    for sx in (-1, 1):
        lo, hi = sorted((sx * 10.51, sx * 13.76))
        h |= box(p, (lo, -1.52, 39.49), (hi, 1.52, 44.21))
        lo, hi = sorted((sx * 10.51, sx * 12.12))
        h |= box(p, (lo, -0.66, 41.76), (hi, 0.66, 44.31))
    out["corner_blocks_axle"] = h
    h = np.zeros(len(p), bool)
    for side in ("audience", "far"):
        q, n = field.logo_panel_face(side)
        n = np.asarray(n)
        u = (q[2] - q[1]); u = u / np.linalg.norm(u)           # not used
        d = (p - q[0]) @ n
        # in-plane: project to plane coords along bottom edge dir and slope dir
        e1 = q[1] - q[0]; e1 /= np.linalg.norm(e1)
        e2 = np.cross(n, e1); e2 /= np.linalg.norm(e2)
        poly = np.c_[(q - q[0]) @ e1, (q - q[0]) @ e2]
        pc = np.c_[(p - q[0]) @ e1, (p - q[0]) @ e2]
        # point in convex quad (CCW check by sign consistency)
        ok = np.ones(len(p), bool)
        sgn = np.sign((poly[1][0]-poly[0][0])*(poly[2][1]-poly[1][1])-(poly[1][1]-poly[0][1])*(poly[2][0]-poly[1][0]))
        for i in range(4):
            a, b = poly[i], poly[(i + 1) % 4]
            cr = (b[0] - a[0]) * (pc[:, 1] - a[1]) - (b[1] - a[1]) * (pc[:, 0] - a[0])
            ok &= cr * sgn >= -1e-9
        h |= ok & (d <= 0.0) & (d >= -0.12)
    out["panels"] = h
    return out


def flower_hits(p):
    h = np.zeros(len(p), bool)
    for f in field.flower_positions():
        x, y = f["xy"]
        h |= (np.hypot(p[:, 0] - x, p[:, 1] - y) <= f["radius"]) & (p[:, 2] <= f["z_range"][1])
    return h


def wall_hits(p, half=72.0, thick=1.5, hgt=12.0):
    ax = np.abs(p[:, 0]) >= half
    ay = np.abs(p[:, 1]) >= half
    inside_slab = (((np.abs(p[:, 0]) >= half) & (np.abs(p[:, 0]) <= half + thick) & (np.abs(p[:, 1]) <= half + thick))
                   | ((np.abs(p[:, 1]) >= half) & (np.abs(p[:, 1]) <= half + thick) & (np.abs(p[:, 0]) <= half + thick)))
    return inside_slab & (p[:, 2] <= hgt)


# ---------------------------------------------------------------- independent CELL hulls
HULLS = []
for al in field.ALLIANCES:
    for wh in field.CELLS:
        pts = field.cell_body_corners(al, wh, ST[al])
        hull = ConvexHull(pts)
        HULLS.append((al, wh, Delaunay(pts), hull))


def hull_inside(p, dil=0.0):
    out = np.zeros(len(p), bool)
    for al, wh, dl, hull in HULLS:
        if dil == 0.0:
            out |= dl.find_simplex(p) >= 0
        else:
            eq = hull.equations
            out |= np.all(p @ eq[:, :3].T + eq[:, 3] <= dil, axis=1)
    return out


def hull_clearance(p):
    """min over hulls of max-plane distance (lower bound of Euclidean distance to the body), per point"""
    best = np.full(len(p), 1e9)
    for al, wh, dl, hull in HULLS:
        eq = hull.equations
        d = (p @ eq[:, :3].T + eq[:, 3]).max(axis=1)
        best = np.minimum(best, d)
    return best


# ---------------------------------------------------------------- targets
def tag_grid(corners, n=9, ring=False):
    c0, c1, c3 = corners[0], corners[1], corners[3]
    u, v = c1 - c0, c3 - c0
    pts = []
    for i in np.linspace(0, 1, n):
        for j in np.linspace(0, 1, n):
            pts.append(c0 + i * u + j * v)
    if ring:   # 0.5 in quiet-zone ring corners + edge midpoints (outside the black square)
        un, vn = u / np.linalg.norm(u), v / np.linalg.norm(v)
        for a in (-0.5, 0.5 + np.linalg.norm(u)):
            for b in (-0.5, 0.5 + np.linalg.norm(v)):
                pts.append(c0 + a * un + b * vn)
    return np.array(pts)


targets = {}
for t in tagkit.KIT_TAGS:
    targets[f"kit{t.id}"] = (tag_grid(tagkit.tag_corners_xyz(t)), 0.25)
    targets[f"kit{t.id}_quietzone_corners"] = (tag_grid(tagkit.tag_corners_xyz(t), n=2, ring=True)[4:], 0.25)
names8 = [n for n, _ in ct.field_reference_points()]
pts8 = np.array([p for _, p in ct.field_reference_points()])
for i, (nm, p) in enumerate(zip(names8, pts8)):
    targets[f"click{i + 1}"] = (p[None], 0.4)
hive = tagkit.hive_tag_defs()
for tid in (34, 35, 36, 37):
    targets[f"hive{tid}"] = (hive[tid], 0.4)    # 4 corners

recs = {o: pl.recommend(o) for o in ("usb", "gopro")}
res = {}
for o in ("usb", "gopro"):
    for k in "AB":
        base = np.array(recs[o]["cameras"][k]["pos"], float)
        variants = [base] + [base + np.array(v) for v in itertools.product((-1, 1), (-1, 1), (-0.5, 0.5))]
        for tname, (P, stop) in targets.items():
            tot = 0
            blocked = {"project_segment_hits_any_cell": 0, "hull": 0, "hull_dil0.5": 0, "frame": 0, "flower": 0, "wall": 0}
            who = {}
            minclear = 1e9
            for cam in variants:
                for p in P:
                    # project function with the same stop-short margin as placement.cell_blocked
                    d = p - cam
                    L = np.linalg.norm(d)
                    end = cam + d * (L - stop) / L
                    tot += 1
                    blocked["project_segment_hits_any_cell"] += int(field.segment_hits_any_cell(cam, end, ST))
                    s = seg_samples(cam, p, stop)
                    blocked["hull"] += int(hull_inside(s).any())
                    blocked["hull_dil0.5"] += int(hull_inside(s, 0.5).any())
                    minclear = min(minclear, float(hull_clearance(s).min()))
                    fh = frame_hits(s)
                    anyf = False
                    for nm, a in fh.items():
                        if a.any():
                            who[nm] = who.get(nm, 0) + 1
                            anyf = True
                    blocked["frame"] += int(anyf)
                    blocked["flower"] += int(flower_hits(s).any())
                    blocked["wall"] += int(wall_hits(s).any())
            res[(o, k, tname)] = (tot, blocked, who, minclear)

lines = []
for o in ("usb", "gopro"):
    for k in "AB":
        lines.append(f"=== option {o} camera {k}, nominal + 8 placement corners (+-1 in, +-0.5 in lens), CALIBRATION_STATE")
        for tname in targets:
            tot, blocked, who, mc = res[(o, k, tname)]
            bad = {a: b for a, b in blocked.items() if b}
            lines.append(f"  {tname:28s} rays {tot:4d}  blocked: {bad if bad else 'none'}  {who if who else ''}  CELL-hull clearance >= {mc:6.2f} in")
txt = "\n".join(lines)
print(txt)
open("evidence/refute/dod9_5/occ5.txt", "w").write(txt)

# wall-top margin for the lowest ray
for o in ("usb",):
    for k in "AB":
        cam = np.array(recs[o]["cameras"][k]["pos"], float)
        worst = 1e9
        for tname, (P, stop) in targets.items():
            for p in P:
                t = (cam[1] - 73.5) / (cam[1] - p[1])        # crossing the wall's outer face y=73.5
                z = cam[2] + t * (p[2] - cam[2])
                worst = min(worst, z)
        print(f"camera {k}: lowest ray height over the audience wall outer face (y=73.5): {worst:.1f} in (wall 12 in)")

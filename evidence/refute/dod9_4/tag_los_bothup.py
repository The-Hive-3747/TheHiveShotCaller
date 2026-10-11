"""Line of sight from the recommended cameras to a grid of points on each kit tag, against the four CELL
boxes (field.point_inside_cell, match-start state: red audience up, blue far up => blue audience CELL is DOWN),
and the frame legs / crossbar (thin cylinders r=1 in). Also where the down CELL box is relative to the panel.
Run: PYTHONPATH=. python evidence/refute/dod9_4/tag_los.py
"""
import numpy as np
from hiveshot import field, tagkit, placement as pl
from hiveshot import field_constants as C

STATES = {"red": field.HiveState("red", "audience"), "blue": field.HiveState("blue", "audience")}


def in_any_cell(p):
    hits = []
    for al, st in STATES.items():
        for which in ("audience", "far"):
            if field.point_inside_cell(p, al, which, st):
                hits.append(f"{al}-{which}")
    return hits


# CELL box extents in field coords (sample)
for al, st in STATES.items():
    for which in ("audience", "far"):
        pts = []
        rng = np.random.default_rng(0)
        c, n, w = field._frame(al, which, st)
        for a in np.linspace(-10, 10, 9):
            for b in np.linspace(-C.CELL_OPENING_HEIGHT / 2, C.CELL_OPENING_HEIGHT / 2, 5):
                for d in np.linspace(0, C.CELL_EXTENT_Y, 7):
                    pts.append(c + a * np.array([1, 0, 0]) + b * w - d * n)
        pts = np.array(pts)
        print(f"{al}-{which}: up={st.up_cell==which}  x {pts[:,0].min():.1f}..{pts[:,0].max():.1f} y {pts[:,1].min():.1f}..{pts[:,1].max():.1f} z {pts[:,2].min():.1f}..{pts[:,2].max():.1f}")

recs = {o: pl.recommend(o) for o in ("usb", "gopro")}
for o, r in recs.items():
    for k in "AB":
        cam = np.array(r["cameras"][k]["pos"], float)
        for t in tagkit.KIT_TAGS:
            cor = tagkit.tag_corners_xyz(t)
            c = cor.mean(0)
            u = cor[1] - cor[0]
            v = cor[3] - cor[0]
            blocked = 0
            total = 0
            who = set()
            for i in np.linspace(0.05, 0.95, 7):
                for j in np.linspace(0.05, 0.95, 7):
                    p = cor[0] + i * u + j * v
                    total += 1
                    hit = False
                    for s in np.linspace(0.0, 0.985, 400):    # stop just before the tag
                        q = cam + s * (p - cam)
                        h = in_any_cell(q)
                        if h:
                            hit = True
                            who.update(h)
                            break
                    blocked += hit
            print(f"{o} cam {k} tag {t.id}: grid points behind a CELL box {blocked}/{total} {sorted(who)}")

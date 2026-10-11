"""Line of sight from the recommended cameras to the 8 click points (CELL opening corners) against the
CELL boxes that are NOT the point's own CELL (match-start state), and the CELL boxes' constants.
Run: PYTHONPATH=. python evidence/refute/dod9_4/click_los.py
"""
import numpy as np
from hiveshot import field, calib_targets as ct, placement as pl
from hiveshot import field_constants as C

print("CELL_EXTENT_Y", C.CELL_EXTENT_Y, "OPENING", C.CELL_OPENING_WIDTH, C.CELL_OPENING_HEIGHT)
STATES = {"red": field.HiveState("red", "audience"), "blue": field.HiveState("blue", "far")}
names = [n for n, _ in ct.field_reference_points()]
pts = np.array([p for _, p in ct.field_reference_points()])
own = ["red-audience"] * 4 + ["blue-far"] * 4
for o in ("usb",):
    r = pl.recommend(o)
    for k in "AB":
        cam = np.array(r["cameras"][k]["pos"], float)
        for n, p, ow in zip(names, pts, own):
            hit = set()
            for s in np.linspace(0.0, 0.99, 600):
                q = cam + s * (p - cam)
                for al, st in STATES.items():
                    for which in ("audience", "far"):
                        tag = f"{al}-{which}"
                        if tag != ow and field.point_inside_cell(q, al, which, st):
                            hit.add(tag)
            print(f"cam {k} {n[:42]:42s} through other CELL boxes: {sorted(hit)}")

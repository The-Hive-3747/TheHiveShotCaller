"""Clearance of rays to the 8 click points / HIVE tags 34-41 from the OTHER three CELL bodies (own CELL skipped),
calibration state, nominal camera spots. Run: PYTHONPATH=. .venv/Scripts/python.exe evidence/refute/dod9_5/occ5b.py"""
import numpy as np
from scipy.spatial import ConvexHull
from hiveshot import field, tagkit, calib_targets as ct, placement as pl
ST = field.CALIBRATION_STATE
H = {}
for al in field.ALLIANCES:
    for wh in field.CELLS:
        H[(al, wh)] = ConvexHull(field.cell_body_corners(al, wh, ST[al])).equations
def clr(s, skip):
    best = 1e9
    for k, eq in H.items():
        if k == skip: continue
        best = min(best, (s @ eq[:, :3].T + eq[:, 3]).max(axis=1).min())
    return best
rec = pl.recommend("usb")
cams = {k: np.array(rec["cameras"][k]["pos"], float) for k in "AB"}
pts = [p for _, p in ct.field_reference_points()]
own = [("red", "audience")] * 4 + [("blue", "audience")] * 4
for k, cam in cams.items():
    out = []
    for i, (p, o) in enumerate(zip(pts, own)):
        t = np.linspace(0, 1, 4000)[:, None]
        s = cam + t * (p - cam)
        out.append(f"{i+1}:{clr(s, o):.2f}")
    print(f"camera {k}: min distance (plane lower bound, in) of ray to click point i from the OTHER 3 CELLs:", " ".join(out))
    hv = tagkit.hive_tag_defs()
    out = []
    for tid in (34, 35, 36, 37, 38, 39, 40, 41):
        if tid not in hv: continue
        o = ("red", "audience") if tid <= 37 else ("blue", "audience")
        c = hv[tid]
        m = 1e9
        for q in c:
            s = cam + np.linspace(0, 0.995, 4000)[:, None] * (q - cam)
            m = min(m, clr(s, o))
        out.append(f"{tid}:{m:.2f}")
    print(f"camera {k}: HIVE tags (own CELL skipped) min clearance from other CELLs:", " ".join(out))

"""Do 6 in tags 100/101 (and their 7 in cards) fit the audience logo panel trapezoid (field.logo_panel_face)?
Run: PYTHONPATH=. .venv/Scripts/python.exe evidence/refute/dod9_5/panel_fit.py"""
import numpy as np
from hiveshot import field, tagkit
q, n = field.logo_panel_face("audience")
n = np.asarray(n)
e1 = (q[1] - q[0]); e1 /= np.linalg.norm(e1)           # bottom edge direction (-X)
e2 = np.cross(n, e1); e2 /= np.linalg.norm(e2)
def to2(P): return np.c_[(P - q[0]) @ e1, (P - q[0]) @ e2]
poly = to2(q)
print("panel quad in-plane (s along bottom edge, t up slope):\n", poly.round(3), " planarity", float(np.abs((q - q[0]) @ n).max()))
def edge_margin(pt):
    m = 1e9
    for i in range(4):
        a, b = poly[i], poly[(i + 1) % 4]
        ed = b - a; L = np.linalg.norm(ed)
        # inward distance for CCW polygon
        m = min(m, (ed[0] * (pt[1] - a[1]) - ed[1] * (pt[0] - a[0])) / L)
    return m
for t in tagkit.KIT_TAGS[:2]:
    c = tagkit.tag_corners_xyz(t)
    off_plane = (c - q[0]) @ n
    p2 = to2(c)
    print(f"tag {t.id}: off-plane {off_plane.round(4).tolist()}  inside margins per corner (in; >0 inside): {[round(edge_margin(p), 3) for p in p2]}")
    # card with 0.5 border
    cen = c.mean(0); r = c[1] - c[0]; r /= np.linalg.norm(r); u = c[0] - c[3]; u /= np.linalg.norm(u)
    h = 3.5
    card = np.array([cen + h * u - h * r, cen + h * u + h * r, cen - h * u + h * r, cen - h * u - h * r])
    print(f"   7 in card margins (negative = hangs over the panel edge): {[round(edge_margin(p), 3) for p in to2(card)]}")
    # CAD top corner block (x 10.51..13.76, y -1.52..1.52, z 39.49..44.21): does the card plane cross it?
    for p in card[:2]:
        pass
    # card top border line lies above the panel top by 0.5 in along the slope: its y,z
    top_mid = cen + 3.5 * u
    print("   card top edge mid (x,y,z):", top_mid.round(3), " card top corners x:", card[:2, 0].round(2), " block face y=1.52: card top y =", round(float(card[0, 1]), 3))
# is the top-edge margin of the black squares tight in the real panel (chamfer)?
print("panel top corner x = +-13.22 per quad; CAD notes chamfer to x 13.7 and tabs to 15.07")

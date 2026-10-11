import sys, numpy as np
from collections import defaultdict
sys.path.insert(0, "tools")
import step_extract as S
from hiveshot import field, tagkit, calib_targets as ct, field_constants as fc
sys.setrecursionlimit(10000)
ents = S.load("data/cad/field-cad-step.zip")
by, pd_name, nauo, xf = S.build(ents)
U = 39.37007874015748
children = defaultdict(list); parents = defaultdict(list)
for n,(p,c,_) in nauo.items():
    children[p].append((n,c)); parents[c].append((n,p))
roots=[pd for pd in pd_name if pd not in parents]
found = {}
def walk(pd, M, path):
    name = pd_name[pd]
    cell = next((p for p in reversed(path) if "Red Cell (Audience)" in p), None)
    if cell and ("Goal Rib" in name or "April Tag" in name):
        v = S.part_vertices(ents, by, pd)
        w = ((M[:3,:3] @ v.T).T + M[:3,3])*U
        found.setdefault(name, []).append((M.copy(), v*U, w))
    for n,c in children.get(pd, []):
        T = S.idt_matrix(ents, xf[n]) if xf.get(n) else np.eye(4)
        walk(c, M@T, path+[name])
for r in roots:
    if "BIOBUZZ" in pd_name[r]: walk(r, np.eye(4), [])
def tofield(p):   # CAD (x lateral, up, z beam) -> field (X=-x, Y=z, Z=up)
    p=np.asarray(p,float); return np.array([-p[0], p[2], p[1]])
# --- sticker
print(list(found)); st = [v for k,v in found.items() if "April Tag" in k][0][0][2]
c_st = tofield(0.5*(st.min(0)+st.max(0)))
print("CAD sticker bbox center (field frame):", c_st.round(3))
# tag row = +0.25 along beam toward opening a_hat = (0, cos30, sin30)
a_hat=np.array([0,np.cos(np.radians(30)),np.sin(np.radians(30))])
row = c_st + 0.25*a_hat
model_tags = field.hive_tag_corners("red","audience",field.HiveState("red","audience"))
mrow = np.mean([v.mean(0) for v in model_tags.values()],axis=0)
print("CAD-derived tag row center:", row.round(3), " field.py:", mrow.round(3), " diff in:", np.linalg.norm(row-mrow).round(3))
print("tag ids -> centers (field.py):", {k: v.mean(0).round(2).tolist() for k,v in model_tags.items()})
# --- ribs (two: front/back). identify the outer one = larger z_beam
ribs = [t for k,v in found.items() if "Goal Rib" in k for t in v]
for M, vloc, w in ribs:
    o = M[:3,3]*U; z_ax = M[:3,2]
    print("rib origin(CAD)", o.round(3), "local z axis (normal)", z_ax.round(3), "local extents min", vloc.min(0).round(3), "max", vloc.max(0).round(3))
M, vloc, w = max(ribs, key=lambda t: t[0][2,3])   # outer rib (largest beam z)
o = M[:3,3]*U; xa, ya, za = M[:3,0], M[:3,1], M[:3,2]
def pt(xl, yl, zl): return tofield(o + xl*xa + yl*ya + zl*za)
# official opening: bottom edge 53.5 and top 65.6 world-up on plane z_loc = 0 (and 0.06 front face)
for zl in (0.0, 0.06):
    # solve yl for world up
    def yl_for_up(up): return (up - o[1] - zl*za[1]) / ya[1]
    yb, yt = yl_for_up(53.5), yl_for_up(65.6)
    ctr = pt(0, (yb+yt)/2, zl)
    corners_cad = np.array([pt(-10, yt, zl), pt(10, yt, zl), pt(10, yb, zl), pt(-10, yb, zl)])  # high-left(-x_cad..)
    # field order high-left (-X side),high-right,low-right,low-left: field X=-x_cad so x_cad=+10 is field -X
    corners_cad = np.array([pt(10, yt, zl), pt(-10, yt, zl), pt(-10, yb, zl), pt(10, yb, zl)])
    mod = np.array([p for _,p in ct.field_reference_points()[:4]])
    print(f"plane z_loc={zl}: official-height opening center (CAD) {ctr.round(3)}; field.py center {np.array(field.cell_opening_plane('red','audience',field.HiveState())[0]).round(3)}")
    print("   corner diffs (in):", np.linalg.norm(corners_cad-mod,axis=1).round(3), " per-axis max |d|:", np.abs(corners_cad-mod).max(0).round(3))
# rib rim vertices: opening rim inner? report rib extents world (field frame)
wf = np.array([tofield(p) for p in w])
print("rib (outer) world bbox field frame min", wf.min(0).round(2), "max", wf.max(0).round(2))
print("field.py HIVE_X", fc.RED_HIVE_X, "CAD red hive x =", (-o[0]).round(3))

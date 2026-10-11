import sys, re, numpy as np
from collections import defaultdict
sys.path.insert(0, "tools")
import step_extract as S
sys.setrecursionlimit(10000)
ents = S.load("data/cad/field-cad-step.zip")
by, pd_name, nauo, xf = S.build(ents)
U = 39.37007874015748
children = defaultdict(list); parents = defaultdict(list)
for n,(p,c,_) in nauo.items():
    children[p].append((n,c)); parents[c].append((n,p))
roots=[pd for pd in pd_name if pd not in parents]
rows=[]
def walk(pd, M, path, inframe):
    name = pd_name[pd]
    inf = inframe or ("Frame" in name and "am-5854" in name)
    if inf:
        v = S.part_vertices(ents, by, pd)
        if len(v):
            w = ((M[:3,:3] @ v.T).T + M[:3,3])*U
            rows.append((name, "/".join(path[-2:]), w))
    for n,c in children.get(pd, []):
        T = S.idt_matrix(ents, xf[n]) if xf.get(n) else np.eye(4)
        walk(c, M@T, path+[name], inf)
for r in roots:
    if "BIOBUZZ" in pd_name[r]: walk(r, np.eye(4), [], False)
print("parts under Frame:", len(rows))
allw = np.vstack([w for _,_,w in rows])
print("FRAME overall CAD (x lateral, y UP, z beam) min", allw.min(0).round(2), "max", allw.max(0).round(2))
from collections import Counter
agg = defaultdict(list)
for n,p,w in rows: agg[n].append(w)
for n,ws in agg.items():
    w=np.vstack(ws); print(f"  {n[:60]:60s} count={len(ws)} min={w.min(0).round(2)} max={w.max(0).round(2)}")
# vertices with y near top
top = allw[allw[:,1] > allw[:,1].max()-3]
print("top vertices (within 3 in of max y): n=",len(top)," x range",top[:,0].min().round(2),top[:,0].max().round(2)," z range",top[:,2].min().round(2),top[:,2].max().round(2))
# distinct high points
for yy in (63.95, 50, 45):
    sel = allw[allw[:,1] > yy]
    print("vertices above y=",yy,":",len(sel), (sel[:,[0,1,2]].min(0).round(2).tolist(), sel.max(0).round(2).tolist()) if len(sel) else "")
# distance from each modelled kit corner / click point 5-8 to the nearest CAD frame vertex (field frame: X=-x, Y=z, Z=up)
F = np.c_[-allw[:,0], allw[:,2], allw[:,1]]
model = {"100 (-X,+Y)": (-24.73,19.475,63.95), "101 (+X,+Y)": (24.73,19.475,63.95), "102 (-X,-Y)": (-24.73,-19.475,63.95), "103 (+X,-Y)": (24.73,-19.475,63.95)}
for n, p in model.items():
    d = np.linalg.norm(F - np.array(p), axis=1)
    j = d.argmin()
    print(f"modelled corner {n} {p}: nearest CAD frame vertex {F[j].round(2).tolist()} at {d[j]:.1f} in")
print("CAD frame highest vertex z:", F[:,2].max().round(2), " model FRAME_TOP_Z 63.95")

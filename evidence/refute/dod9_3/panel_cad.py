import sys, numpy as np
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
    inf = inframe or ("am-5854" in name)
    if inf and any(k in name for k in ("Panel","Foot Bar","Top Bar","Top Corner")):
        v = S.part_vertices(ents, by, pd)
        if len(v):
            w = ((M[:3,:3] @ v.T).T + M[:3,3])*U
            rows.append((name, w))
    for n,c in children.get(pd, []):
        T = S.idt_matrix(ents, xf[n]) if xf.get(n) else np.eye(4)
        walk(c, M@T, path+[name], inf)
for r in roots:
    if "BIOBUZZ" in pd_name[r]: walk(r, np.eye(4), [], False)
for name, w in rows:
    F = np.c_[-w[:,0], w[:,2], w[:,1]]   # field: X=-x, Y=z, Z=up (per predecessor)
    if F[:,1].mean() > 0 or 'Panel' not in name:
        if ('Panel' in name and F[:,1].mean()>0) or ('Foot Bar' in name and F[:,0].mean()>0 and F[:,1].mean()>0 or 'Foot Bar' in name):
            print(name, "nv", len(F), "min", F.min(0).round(3), "max", F.max(0).round(3))
            if 'Panel' in name:
                u = np.unique(F.round(3), axis=0)
                print(" unique verts:", len(u))
                for p in u[:40]: print("   ", p)

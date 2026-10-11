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
rows=defaultdict(list)
def walk(pd, M, path):
    name = pd_name[pd]
    key = None
    if any("Perimeter" in p or "Panel" in p for p in path+[name]):
        key = "perimeter"
    if "Soft Tiles" in name: key="tiles"
    if "Side Glass" in name: key = "glass"
    if key:
        v = S.part_vertices(ents, by, pd)
        if len(v):
            w = ((M[:3,:3] @ v.T).T + M[:3,3])*U
            rows[key].append((name, w))
    for n,c in children.get(pd, []):
        T = S.idt_matrix(ents, xf[n]) if xf.get(n) else np.eye(4)
        walk(c, M@T, path+[name])
for r in roots:
    if "BIOBUZZ" in pd_name[r]: walk(r, np.eye(4), [])
for k, lst in rows.items():
    a = np.vstack([w for _, w in lst]); print(k, len(lst), "parts; bbox (x, up, z) min", a.min(0).round(2), "max", a.max(0).round(2))
# perimeter: wall thickness estimate: at x extremes
per = np.vstack([w for _, w in rows["perimeter"]])
xs = per[:,0]; zs = per[:,2]
for ax, nm in ((0,"x"),(2,"z")):
    v = per[:,ax]
    hi = v[v > v.max()-4]; print(nm, "max side: vertex spread near outer face:", np.unique(hi.round(2))[-12:], "...")
# per-part widths
from collections import Counter
print(Counter(n for n,_ in rows["perimeter"]).most_common(12))
print("---- +X side parts (center x > 60)")
seen=set()
for key in ("perimeter","glass"):
    for n,w in rows[key]:
        c = w.mean(0)
        if c[0] > 60 and abs(c[2]) < 60:
            ext = (w.min(0), w.max(0))
            nm = n[:50]
            if "rivet" in nm.lower() or "Pin" in n: continue
            print(key, nm, "x range %.2f..%.2f"%(ext[0][0], ext[1][0]), "up %.2f..%.2f"%(ext[0][1], ext[1][1]), "z %.1f..%.1f"%(ext[0][2], ext[1][2]))

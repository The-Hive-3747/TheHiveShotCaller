import numpy as np
from hiveshot import placement as pl, tagkit, calib_targets as ct
FL = {  # field-frame boxes (X, Y, Z) lo/hi
 "aud (-X side)": ([-26.73, 65.63, 0], [-20.06, 71.79, 22.65]),
 "side +X (y~23)": ([65.63, 20.06, 0], [71.79, 26.73, 22.65]),
 "side -X (y~-23)": ([-71.79, -26.73, 0], [-65.63, -20.06, 22.65]),
 "far (+X side)": ([20.06, -71.79, 0], [26.73, -65.63, 22.65]),
}
def seg_box(p0, p1, lo, hi):
    d = p1 - p0
    tmin, tmax = 0.0, 1.0
    for i in range(3):
        if abs(d[i]) < 1e-12:
            if p0[i] < lo[i] or p0[i] > hi[i]: return False
        else:
            t1, t2 = (lo[i]-p0[i])/d[i], (hi[i]-p0[i])/d[i]
            if t1 > t2: t1, t2 = t2, t1
            tmin, tmax = max(tmin, t1), min(tmax, t2)
            if tmin > tmax: return False
    return True
rec = pl.recommend("usb")
pts = pl._stack(pl.sample_trajectories())
print("n ball sample points", len(pts))
targets = {"ball": pts}
for k in "AB":
    cp = np.array(rec["cameras"][k]["pos"], float)
    for name, (lo, hi) in FL.items():
        lo, hi = np.array(lo), np.array(hi)
        blocked = np.mean([seg_box(cp, p, lo, hi) for p in pts])
        print(f"cam {k} flower {name}: fraction of ball sample points whose ray passes through the flower BOX {blocked:.3f}")
    # tags / refs
    names = {}
    for t in tagkit.KIT_TAGS: names[f"kit {t.id}"] = tagkit.tag_corners_xyz(t).mean(0)
    for n, p in ct.field_reference_points(): names[n[:30]] = np.array(p)
    for n, p in names.items():
        for fn, (lo, hi) in FL.items():
            if seg_box(cp, p, np.array(lo), np.array(hi)): print(f"  cam {k} -> {n}: ray through flower {fn}")

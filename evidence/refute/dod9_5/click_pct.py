import numpy as np
from hiveshot import placement as pl, calib_targets as ct
W, H = pl.RESOLUTION
pts = np.array([p for _, p in ct.field_reference_points()])
print([n for n,_ in ct.field_reference_points()])
for opt in ("gopro", "usb"):
    r = pl.recommend(opt)
    for k in "AB":
        c = r["cameras"][k]
        cam = pl._vcam(c["pos"], c["look_at"], c["hfov_deg"])
        u, v = cam.project(pts)
        print(opt, k, " ".join(f"{i+1}:{round(100*a/W)}/{round(100*b/H)}" for i, (a, b) in enumerate(zip(u, v))),
              "margin px min", round(min(u.min(), v.min(), W-u.max(), H-v.max())))

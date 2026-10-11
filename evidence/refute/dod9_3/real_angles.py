import sys, numpy as np, math
sys.path.insert(0, "evidence/refute/dod9_3")
import sim3
from hiveshot import placement as pl, tagkit
for opt in ("usb", "gopro"):
    r = pl.recommend(opt)
    for k in "AB":
        cam = pl._vcam(r["cameras"][k]["pos"], r["cameras"][k]["look_at"], r["cameras"][k]["hfov_deg"])
        pos = np.array(r["cameras"][k]["pos"], float)
        for tid, sx in ((100, -1), (101, 1)):
            c = sim3.real_panel_corners(sx)
            nrm = np.cross(c[1]-c[0], c[0]-c[3]); nrm /= np.linalg.norm(nrm)
            # ensure facing +y
            if nrm[1] < 0: nrm = -nrm
            ray = pos - c.mean(0); ray /= np.linalg.norm(ray)
            ang = math.degrees(math.acos(ray @ nrm))
            u, v = cam.project(c); uv = np.c_[u, v]
            edge = np.linalg.norm(uv - np.roll(uv, -1, 0), axis=1).min()
            mc = tagkit.tag_corners_xyz(tid); ray2 = pos - mc.mean(0); ray2 /= np.linalg.norm(ray2)
            print(opt, k, tid, "REAL-tilt tag angle %.1f deg (model %.1f), min edge %.1f px, normal %s" % (ang, math.degrees(math.acos(ray2 @ tagkit.tag_normal_xyz(tid))), edge, nrm.round(3)))

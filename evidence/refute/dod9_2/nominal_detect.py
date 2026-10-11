import sys; sys.path.insert(0, "evidence/refute/dod9_2")
import numpy as np
from sim import *
for opt in ("usb","gopro"):
    for k in "AB":
        c = pl.recommend(opt)["cameras"][k]
        cam = VirtualCamera(*pl.camera_from_pose(c["pos"], c["look_at"], c["hfov_deg"], W, H, "cam0" if k=="A" else "cam1"))
        up = {i: v for i, v in tagkit.hive_tag_defs().items() if 34 <= i <= 37}
        world = {**tagkit.tag_defs(), **up}
        for seed in (0,1,2):
            im = render(cam, world, seed)
            d = calib.detect_apriltags(im)
            print(opt, k, seed, sorted(x["id"] for x in d))
        # rendering only the CELL tags alone
        im = render(cam, up, 0); print("   up-only", sorted(x["id"] for x in calib.detect_apriltags(im)))
        # min edges
        for tid,cn in up.items():
            u,v = cam.project(cn); q=np.c_[u,v]; e=[np.linalg.norm(q[i]-q[(i+1)%4]) for i in range(4)]
            print("   tag",tid,"edges px %.1f..%.1f"%(min(e),max(e)), end=";")
        print()

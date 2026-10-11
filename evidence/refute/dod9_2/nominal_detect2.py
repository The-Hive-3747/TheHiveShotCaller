import sys; sys.path.insert(0, "evidence/refute/dod9_2")
import numpy as np
from sim import *
opt="usb"
c = pl.recommend(opt)["cameras"]["B"]
cam = VirtualCamera(*pl.camera_from_pose(c["pos"], c["look_at"], c["hfov_deg"], W, H, "cam1"))
up = {i: v for i, v in tagkit.hive_tag_defs().items() if 34 <= i <= 37}
kit = tagkit.tag_defs()
for name, world in (("kit only", kit), ("kit+up", {**kit, **up})):
    im = render(cam, world, 0)
    print(name, sorted(x["id"] for x in calib.detect_apriltags(im)))
    cv2.imwrite(f"evidence/refute/dod9_2/B_{name.replace(' ','_').replace('+','_')}.png", im)
for t in (100,101,102,103):
    u,v=cam.project(kit[t]); print(t, np.c_[u,v].round(0).tolist())
for t in (34,35,36,37):
    u,v=cam.project(up[t]); print(t, np.c_[u,v].round(0).tolist()[0], np.c_[u,v].round(0).tolist()[2])

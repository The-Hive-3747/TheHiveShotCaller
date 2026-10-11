import numpy as np
from hiveshot import placement as pl, calib
W,H=1920,1080
real={"100 (-13.74,+1.52,44.2)":(-13.74,1.52,44.2),"101":(13.74,1.52,44.2),"102":(-13.74,-1.52,44.2),"103":(13.74,-1.52,44.2),
      "foot corner (-24.73,19.475,2)":(-24.73,19.475,2.15),"foot (24.73,19.475,2)":(24.73,19.475,2.15), "model top corner (24.73,19.475,63.95)":(24.73,19.475,63.95)}
for opt in ("usb","gopro"):
    for k in "AB":
        c=pl.recommend(opt)["cameras"][k]; cam=pl._vcam(c["pos"],c["look_at"],c["hfov_deg"])
        print(opt,k,{n:"%.0f/%.0f"%tuple(np.array([calib.project(cam.intr,cam.extr,np.array([p],float))[0]])[0]/[W,H]*100) for n,p in real.items()})

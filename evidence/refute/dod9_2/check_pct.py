import math, numpy as np
from hiveshot import placement as p, field, calib_targets as ct, tagkit, calib
W,H=1920,1080
for opt in ("gopro","usb"):
    r=p.recommend(opt)
    for k in ("A","B"):
        c=r["cameras"][k]; cam=p._vcam(c["pos"],c["look_at"],c["hfov_deg"])
        def pct(xyz):
            uv=calib.project(cam.intr,cam.extr,np.array([xyz],float))[0]; return "%.0f/%.0f"%(uv[0]/W*100,uv[1]/H*100), uv
        print("==",opt,k)
        cen=field.cell_opening_plane("red","audience",field.HiveState())[0]
        print(" CELLctr",pct(cen)[0])
        tg=tagkit.up_cell_tag_corners()
        pcs=[pct(np.mean(v,axis=0)) for _,v in sorted(tg.items())]
        print(" CELL tags",[a for a,_ in pcs])
        print(" kit",{t:pct(tagkit.tag_center_xyz(t))[0] for t in (100,101,102,103)})
        for i,(n,xyz) in enumerate(ct.field_reference_points(),1):
            s,uv=pct(xyz); print("  pt",i,s)
        # bar slope: pts 5,6
        pts=ct.field_reference_points()
        u5=pct(pts[4][1])[1]; u6=pct(pts[5][1])[1]
        d=u6-u5  # +X end minus -X end
        print(" bar slope deg (img, y down):",math.degrees(math.atan2(d[1],d[0])), "dx,dy",d)

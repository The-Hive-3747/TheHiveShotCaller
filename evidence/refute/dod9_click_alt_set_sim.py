import sys, numpy as np
sys.path.insert(0,"tests")
import test_tagkit as T
from hiveshot import calib, calib_targets, field, placement as pl
red=[p for n,p in calib_targets.field_reference_points()][:4]
alt=np.array(red+[(-24.73,19.47,0),(24.73,19.47,0),(-13.22,1.666,40.024),(13.22,1.666,40.024)],float)
print(field.frame_reference_points().keys() if hasattr(field.frame_reference_points(),'keys') else '')
for o in ("gopro","usb"):
    for k in "AB":
        cam=T._vcam(o,k); u,v=cam.project(alt); d=cam.depth(alt)
        pos=pl._cam_pos(cam) if hasattr(pl,'_cam_pos') else None
        print(o,k,[f"{100*a/1920:.0f}/{100*b/1080:.0f}" for a,b in zip(u,v)], "blocked",pl.cell_blocked(pos,alt,field.CALIBRATION_STATE,skip=(("red","audience"),)).tolist())
SIG=(1.0,1.5,2.0)
for o in ("gopro","usb"):
    for sig in SIG:
        ok=n=ref=0; errs=[]
        cams={k:T._vcam(o,k) for k in "AB"}
        proj={k:np.c_[cams[k].project(alt)] for k in "AB"}
        centre,_=field.cell_opening_plane("red","audience",field.CALIBRATION_STATE["red"])
        uvc={k:np.c_[cams[k].project(np.array([centre]))] for k in "AB"}
        for sd in range(100):
            rng=np.random.default_rng(7000+sd); ext={}
            for k in "AB":
                n+=1; cl=proj[k]+rng.normal(0,sig,proj[k].shape)
                try: e=calib.solve_extrinsics_from_points(cams[k].intr,cl,alt,cams[k].cam_id)
                except ValueError: ref+=1; continue
                per=np.array(calib.reprojection_report(cams[k].intr,e,cl,alt)["per_point_px"])
                rm=calib.reprojection_report(cams[k].intr,e,cl,alt)["rmse_px"]
                ok+=bool(rm<2 and per.max()<3); ext[k]=e
            if len(ext)==2:
                est,_=calib.triangulate(cams["A"].intr,ext["A"],uvc["A"],cams["B"].intr,ext["B"],uvc["B"]); errs.append(np.linalg.norm(est[0]-centre))
        print(o,sig,"gate %d/%d"%(ok,n),"refused",ref,"center med %.2f max %.2f"%(np.median(errs),np.max(errs)))

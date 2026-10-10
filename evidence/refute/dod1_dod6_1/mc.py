import sys, numpy as np
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker")
from hiveshot import calib, placement as pl, calib_targets as ct
ref=ct.field_reference_points(); F=np.array([p for _,p in ref])
IA,EA=pl.camera_from_pose((-78,65,36),(-13,41,61),86,1920,1080,'A')
IB,EB=pl.camera_from_pose((65,78,36),(-13,41,61),86,1920,1080,'B')
tests={'opening center':np.array([-12.8,24.2,59.5]),'launch zone (-13,55,30)':np.array([-13.,55.,30.]),'mid flight (-13,40,70)':np.array([-13.,40.,70.])}
rng=np.random.default_rng(1)
for sig in (0.5,1.0,2.0,3.0):
    errs={k:[] for k in tests}; rm=[]
    for _ in range(300):
        ea=calib.solve_extrinsics_from_points(IA,calib.project(IA,EA,F)+rng.normal(0,sig,(8,2)),F,'A')
        eb=calib.solve_extrinsics_from_points(IB,calib.project(IB,EB,F)+rng.normal(0,sig,(8,2)),F,'B')
        rm.append((ea.rmse_in,eb.rmse_in))
        for k,P in tests.items():
            ua=calib.project(IA,EA,P[None])[0]; ub=calib.project(IB,EB,P[None])[0]
            x,_=calib.triangulate(IA,ea,ua,IB,eb,ub); errs[k].append(np.linalg.norm(x-P))
    print('click noise %.1f px: reported rmse_in A/B mean %.2f/%.2f |'%(sig,*np.mean(rm,0)), ' | '.join('%s: median %.2f in, p95 %.2f in'%(k,np.median(v),np.percentile(v,95)) for k,v in errs.items()))

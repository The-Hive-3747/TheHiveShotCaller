import sys, json, time, math, numpy as np
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker")
from rh import *
from hiveshot import calib, placement as pl, calib_targets as ct
from hiveshot.models import CameraIntrinsics
P=8771
print('up', wait_up(P))
s,cal=call('GET',P,'/api/calib'); print('persisted calib cams', [i['cam_id'] for i in cal['intrinsics']], 'extrinsics', [ (e['cam_id'], round(e['rmse_in'],2)) for e in cal['extrinsics']])
UI_NAMES=['Red HIVE up-CELL opening, high-left corner','Red HIVE up-CELL opening, high-right corner','Red HIVE up-CELL opening, low-right corner','Red HIVE up-CELL opening, low-left corner','HIVE frame base corner (-X, -Y)','HIVE frame base corner (+X, +Y)','Tile intersection (-48, -48)','Tile intersection (+48, +48)']
ref=ct.field_reference_points()
print('backend names now:'); [print('  ',i+1,n) for i,(n,_) in enumerate(ref)]
print('UI-hardcoded names not known by backend:', [n for n in UI_NAMES if n.lower() not in {r[0].lower() for r in ref}])
pos={'cam0':(-78,65,36),'cam1':(65,78,36)}
rng=np.random.default_rng(11)
# UI request (old hardcoded names)
cam='cam0'; I=[CameraIntrinsics(**i) for i in cal['intrinsics'] if i['cam_id']==cam][0]
hf=math.degrees(2*math.atan(960/I.fx)); _,E=pl.camera_from_pose(pos[cam],(-13,41,61),hf,1920,1080,cam)
uv=calib.project(I,E,np.array([p for _,p in ref]))
pts_ui=[{'u':float(u),'v':float(v),'name':n} for n,(u,v) in zip(UI_NAMES,uv)]
print('POST with the UI\'s hardcoded names ->', call('POST',P,f'/api/calib/extrinsics/{cam}',{'points':pts_ui}))
for cam in ('cam0','cam1'):
    I=[CameraIntrinsics(**i) for i in cal['intrinsics'] if i['cam_id']==cam][0]
    hf=math.degrees(2*math.atan(960/I.fx)); _,E=pl.camera_from_pose(pos[cam],(-13,41,61),hf,1920,1080,cam)
    uv=calib.project(I,E,np.array([p for _,p in ref])); 
    inframe=[bool(0<=u<1920 and 0<=v<1080) for u,v in uv]
    noisy=uv+rng.normal(0,1.0,uv.shape)
    pts=[{'u':float(u),'v':float(v),'name':n} for (n,_),(u,v) in zip(ref,noisy)]
    t=time.time(); s,r=call('POST',P,f'/api/calib/extrinsics/{cam}',{'points':pts}); print(cam,'in frame',inframe,'->',s,'rmse_in',r.get('rmse_in'),'max err_px',max(p['err_px'] for p in r['per_point']) if s==200 else r,'%.2fs'%(time.time()-t))
    if s==200:
        sol=[e for e in call('GET',P,'/api/calib')[1]['extrinsics'] if e['cam_id']==cam][0]
        print('   solved tvec',np.round(sol['tvec'],1),'true tvec',np.round(E.tvec,1))

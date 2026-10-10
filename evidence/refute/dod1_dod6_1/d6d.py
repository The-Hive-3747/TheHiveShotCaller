import sys, json, time, math, urllib.request, numpy as np
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker")
from rh import *
from hiveshot import calib, placement as pl
from hiveshot.models import CameraIntrinsics, CameraExtrinsics
P=8771; T0=time.time()
print('up', wait_up(P))
# step 0: checkerboard
d=urllib.request.urlopen(f'http://127.0.0.1:{P}/api/calib/checkerboard.pdf'); b=d.read()
print('checkerboard.pdf', d.status, d.headers.get('Content-Type'), len(b),'bytes', b[:8], b'MediaBox' in b, b[b.find(b'MediaBox'):b.find(b'MediaBox')+40])
open('checkerboard.pdf','wb').write(b)
s,pts=call('GET',P,'/api/calib/points'); print('points', s, [p['name'] for p in pts])
SPd=r"C:\Users\3747h\AppData\Local\Temp\claude\C--Users-3747h-Documents-HiveShotTracker\386da1de-9207-4304-8c4f-9284e5732d29\scratchpad\refute16"
src=[{'cam_id':c,'kind':'file','target':rf"{SPd}\board_{c}.mp4",'width':1920,'height':1080,'fps_hint':60,'loop':True,'realtime':True} for c in ('cam0','cam1')]
print('PUT',call('PUT',P,'/api/config',{'sources':src})[0]); print('start',call('POST',P,'/api/pipeline/start')[0]); time.sleep(2)
t_ops=time.time()
for c in ('cam0','cam1'):
    call('POST',P,f'/api/calib/intrinsics/{c}/start'); time.sleep(20)
    t=time.time(); s,r=call('POST',P,f'/api/calib/intrinsics/{c}/stop'); print(c,'intrinsics',s,r,'solve %.1fs'%(time.time()-t))
s,cal=call('GET',P,'/api/calib')
pos={'cam0':(-78,65,36),'cam1':(65,78,36)}; rng=np.random.default_rng(21)
for c in ('cam0','cam1'):
    I=[CameraIntrinsics(**i) for i in cal['intrinsics'] if i['cam_id']==c][0]
    hf=math.degrees(2*math.atan(960/I.fx)); _,E=pl.camera_from_pose(pos[c],(-13,41,61),hf,1920,1080,c)
    uv=calib.project(I,E,np.array([p['xyz'] for p in pts]))+rng.normal(0,1.5,(8,2))
    body={'points':[{'u':float(u),'v':float(v),'name':p['name']} for p,(u,v) in zip(pts,uv)]}
    t=time.time(); s,r=call('POST',P,f'/api/calib/extrinsics/{c}',body); print(c,'extrinsics',s,'rmse_in %.3f'%r['rmse_in'],'max px %.2f'%max(q['err_px'] for q in r['per_point']),'%.2fs'%(time.time()-t))
print('machine time for calibration steps (excl. human): %.0f s'%(time.time()-t_ops))
print(call('POST',P,'/api/pipeline/stop')[0])
print('stale flags', [e['stale'] for e in call('GET',P,'/api/calib')[1]['extrinsics']])

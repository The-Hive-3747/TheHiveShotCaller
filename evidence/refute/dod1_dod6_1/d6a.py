from rh import *
src=[{'cam_id':'cam0','kind':'device','target':0,'width':640,'height':480,'fps_hint':30},
     {'cam_id':'cam1','kind':'file','target':'fixtures/synth_basic/cam1.mp4','width':1920,'height':1080,'fps_hint':60,'loop':True,'realtime':True}]
print('PUT',call('PUT',8770,'/api/config',{'sources':src})[0])
print('start',call('POST',8770,'/api/pipeline/start')[0]); time.sleep(2)
print('intr stop w/o start', call('POST',8770,'/api/calib/intrinsics/cam0/stop'))
t=time.time(); print('intr start', call('POST',8770,'/api/calib/intrinsics/cam0/start')); time.sleep(20)
t1=time.time(); r=call('POST',8770,'/api/calib/intrinsics/cam0/stop'); print('intr stop', r, 'stop took %.2fs'%(time.time()-t1))
print('extrinsics without intrinsics', call('POST',8770,'/api/calib/extrinsics/cam0',{'points':[{'u':1,'v':1,'name':'x'}]}))
print('preview jpg', end=' ')
import urllib.request
d=urllib.request.urlopen('http://127.0.0.1:8770/api/preview/cam0.jpg'); b=d.read(); print(d.status, len(b), d.headers.get('X-Frame-Width'), d.headers.get('X-Frame-Height'))
open('cam0_preview.jpg','wb').write(b)
print(call('POST',8770,'/api/pipeline/stop')[0])
print(call('GET',8770,'/api/calib'))

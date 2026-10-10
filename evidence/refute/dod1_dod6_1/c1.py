from rh import *
import subprocess
# C1: rtmp kind with bare name targets, no publisher
src=[{'cam_id':'cam0','kind':'rtmp','target':'cam0','width':1920,'height':1080,'fps_hint':60},
     {'cam_id':'cam1','kind':'rtmp','target':'cam1','width':1920,'height':1080,'fps_hint':60}]
print('PUT',call('PUT',8770,'/api/config',{'sources':src})[0])
print('start',call('POST',8770,'/api/pipeline/start')[0])
for i in range(6):
    time.sleep(1.5); st=cams(8770); print(i, brief(st)); 
print(st['rtmp'])
print('stop',call('POST',8770,'/api/pipeline/stop'))

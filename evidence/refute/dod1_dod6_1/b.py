from rh import *
src=[{'cam_id':'cam0','kind':'device','target':0,'width':640,'height':480,'fps_hint':30},
     {'cam_id':'cam1','kind':'file','target':'fixtures/synth_basic/cam1.mp4','width':1920,'height':1080,'fps_hint':60,'loop':True,'realtime':True}]
s,c=call('PUT',8770,'/api/config',{'sources':src}); print('PUT',s,[ (x['cam_id'],x['kind'],x['target']) for x in c['sources']])
t=time.time(); print('start',call('POST',8770,'/api/pipeline/start')[0], round(time.time()-t,2))
for i in range(11):
    time.sleep(1); print(i, brief(cams(8770))['cams'])
print('PUT sources while running', call('PUT',8770,'/api/config',{'sources':src[:1]}))
print('PUT benign while running', call('PUT',8770,'/api/config',{'burst_gap_s':1.5})[0])
t=time.time(); print('stop',call('POST',8770,'/api/pipeline/stop'), round(time.time()-t,2))
print(brief(cams(8770)))

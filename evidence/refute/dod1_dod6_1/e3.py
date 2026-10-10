from rh import *
F=lambda c,k,t:{'cam_id':c,'kind':k,'target':t,'width':1920,'height':1080,'fps_hint':60,'loop':True,'realtime':True}
FILES=[F('cam0','file','fixtures/synth_basic/cam0.mp4'),F('cam1','file','fixtures/synth_basic/cam1.mp4')]
call('POST',8770,'/api/pipeline/stop')
print('PUT kind=banana', call('PUT',8770,'/api/config',{'sources':[dict(FILES[0],kind='banana'),FILES[1]]})[0])
r=call('POST',8770,'/api/pipeline/start'); print('start with kind=banana:', r)
print(brief(cams(8770))['running'])
call('POST',8770,'/api/pipeline/stop')
print('dup cam ids start -> running?')
print('PUT dup', call('PUT',8770,'/api/config',{'sources':[FILES[0],dict(FILES[1],cam_id='cam0')]})[0])
r=call('POST',8770,'/api/pipeline/start'); print(' start', r[0]); time.sleep(2); print(' ', brief(cams(8770))); print(call('POST',8770,'/api/pipeline/stop')[0])
print('restore', call('PUT',8770,'/api/config',{'sources':FILES})[0])

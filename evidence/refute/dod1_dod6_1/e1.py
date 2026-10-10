from rh import *
import subprocess
def procs():
    out=subprocess.run(['tasklist'],capture_output=True,text=True).stdout
    return [l.split()[0]+":"+l.split()[1] for l in out.splitlines() if any(k in l.lower() for k in ('mediamtx','ffmpeg'))]
F=lambda c,k,t:{'cam_id':c,'kind':k,'target':t,'width':1920,'height':1080,'fps_hint':60,'loop':True,'realtime':True}
FILES=[F('cam0','file','fixtures/synth_basic/cam0.mp4'),F('cam1','file','fixtures/synth_basic/cam1.mp4')]
RT=[F('cam0','rtmp','rtmp://127.0.0.1:1935/cam0'),F('cam1','rtmp','rtmp://127.0.0.1:1935/cam1')]
DEV=[dict(F('cam0','device',0),width=640,height=480,fps_hint=30),FILES[1]]
print('state', brief(cams(8770))['running'], procs())
print('stop', call('POST',8770,'/api/pipeline/stop')[0], 'procs after stop', procs())
# (e1) bad device index
print('PUT bad device', call('PUT',8770,'/api/config',{'sources':[dict(DEV[0],target=7),FILES[1]]})[0])
r=call('POST',8770,'/api/pipeline/start'); print('start bad dev', r[0], r[1] if r[0]!=200 else '')
time.sleep(4); b=brief(cams(8770)); print(' ', b['running'], {k:(v['frames_read'],v['is_alive'],(v['last_error'] or '')[:70], v['reconnects']) for k,v in b['cams'].items()})
print(' stop', call('POST',8770,'/api/pipeline/stop')[0], procs())
# bad kind / garbage
print('PUT kind=banana', call('PUT',8770,'/api/config',{'sources':[dict(FILES[0],kind='banana')]}))
print('PUT device target "abc"', call('PUT',8770,'/api/config',{'sources':[dict(DEV[0],target='abc'),FILES[1]]})[0])
r=call('POST',8770,'/api/pipeline/start'); print(' start named device', r[0]); time.sleep(3); b=brief(cams(8770)); print(' ', {k:(v['frames_read'],v['is_alive'],(v['last_error'] or '')[:70]) for k,v in b['cams'].items()}); call('POST',8770,'/api/pipeline/stop')
print('PUT file missing', call('PUT',8770,'/api/config',{'sources':[dict(FILES[0],target='nope.mp4'),FILES[1]]})[0])
r=call('POST',8770,'/api/pipeline/start'); print(' start', r[0]); time.sleep(3); b=brief(cams(8770)); print(' ', b['running'], {k:(v['frames_read'],v['is_alive'],(v['last_error'] or '')[:70],v['ended']) for k,v in b['cams'].items()}); print(' stop', call('POST',8770,'/api/pipeline/stop')[0])
# (d) switch device -> rtmp -> files -> device while stopped, restart each
for name,s in (('device',DEV),('rtmp',RT),('files',FILES),('device',DEV)):
    print('SWITCH ->',name, call('PUT',8770,'/api/config',{'sources':s})[0])
    r=call('POST',8770,'/api/pipeline/start'); time.sleep(5); b=brief(cams(8770))
    print(' start',r[0], b['running'], 'rtmp',b['rtmp'], {k:(v['frames_read'],v['is_alive']) for k,v in b['cams'].items()})
    print(' stop', call('POST',8770,'/api/pipeline/stop')[0], procs())
# (e3) stop/start x3 with rtmp
call('PUT',8770,'/api/config',{'sources':RT})
for i in range(3):
    r=call('POST',8770,'/api/pipeline/start'); time.sleep(2); print('cycle',i,'start',r[0],'rtmp',brief(cams(8770))['rtmp'],procs())
    t=time.time(); r=call('POST',8770,'/api/pipeline/stop'); print('   stop',r[0],round(time.time()-t,2),'procs',procs())
# double start / double stop
print('double start', call('POST',8770,'/api/pipeline/start')[0], call('POST',8770,'/api/pipeline/start')[0], call('POST',8770,'/api/pipeline/stop')[0], call('POST',8770,'/api/pipeline/stop')[0], procs())

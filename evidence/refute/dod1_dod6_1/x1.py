from rh import *
import subprocess
P=8770
def procs():
    out=subprocess.run(['tasklist'],capture_output=True,text=True).stdout
    return [l.split()[0]+":"+l.split()[1] for l in out.splitlines() if any(k in l.lower() for k in ('mediamtx','ffmpeg'))]
print('up',wait_up(P)); print('devices', call('GET',P,'/api/devices')[1], call('GET',P,'/api/devices')[1])
DEV=[{'cam_id':'cam0','kind':'device','target':0,'width':640,'height':480,'fps_hint':30},
     {'cam_id':'cam1','kind':'file','target':'fixtures/synth_basic/cam1.mp4','width':1920,'height':1080,'fps_hint':60,'loop':True,'realtime':True}]
print('PUT dev', call('PUT',P,'/api/config',{'sources':DEV})[0]); print('start',call('POST',P,'/api/pipeline/start')[0]); time.sleep(5)
print('device (exe):', {k:(v['frames_read'],round(v['fps'],1),v['is_alive'],v['last_error']) for k,v in brief(cams(P))['cams'].items()}); print('stop',call('POST',P,'/api/pipeline/stop')[0])
RT=[{'cam_id':c,'kind':'rtmp','target':f'rtmp://127.0.0.1:1935/{c}','width':1920,'height':1080,'fps_hint':60} for c in ('cam0','cam1')]
print('PUT rtmp', call('PUT',P,'/api/config',{'sources':RT})[0]); print('start',call('POST',P,'/api/pipeline/start')[0]); st=cams(P); print('rtmp status',st['rtmp'],procs())

from rh import *
src=[{'cam_id':'cam0','kind':'rtmp','target':'rtmp://127.0.0.1:1935/cam0','width':1920,'height':1080,'fps_hint':60},
     {'cam_id':'cam1','kind':'rtmp','target':'rtmp://127.0.0.1:1935/cam1','width':1920,'height':1080,'fps_hint':60}]
print('PUT',call('PUT',8770,'/api/config',{'sources':src})[0])
print('start',call('POST',8770,'/api/pipeline/start')[0])
for i in range(8):
    time.sleep(1.5); st=cams(8770); b=brief(st); print(i, {k:(v['frames_read'],v['is_alive'],v['reconnects'],v['last_error']) for k,v in b['cams'].items()}, b['rtmp'])

from rh import *
t0=time.time()
for i in range(16):
    time.sleep(4); st=cams(8770); b=brief(st)
    print(round(time.time()-t0), {k:(v['frames_read'],v['is_alive'],(v['last_error'] or '')[:20]) for k,v in b['cams'].items()}, 'shot', st['last_shot_id'])
s,ss=call('GET',8770,'/api/sessions')
for x in ss:
    s,sh=call('GET',8770,f"/api/sessions/{x['session_id']}/shots"); print(x['session_id'], len(sh), [(h['result'],round(h['exit_speed_mps'] or 0,1)) for h in sh][:12])

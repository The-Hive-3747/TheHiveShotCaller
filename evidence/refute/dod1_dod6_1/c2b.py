from rh import *
t0=time.time()
for i in range(14):
    time.sleep(2); st=cams(8770); b=brief(st); print(round(time.time()-t0), {k:(v['frames_read'],round(v['fps'] or 0,1),v['is_alive'],v['reconnects'],(v['last_error'] or '')[:40]) for k,v in b['cams'].items()}, 'last_shot', st.get('last_shot_id'), 'det_fps', st.get('detector_fps'), 'mism', st.get('calibration_mismatch'), st.get('last_error'))

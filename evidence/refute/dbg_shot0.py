import json, sys, time, tempfile
from pathlib import Path
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker")
from hiveshot import config as cfgmod
from hiveshot.pipeline import Pipeline
from hiveshot.store import Store
fx = Path(sys.argv[1]); tmp = Path(tempfile.mkdtemp(prefix="refute_"))
cfg = cfgmod.AppConfig(sources=[cfgmod.SourceConfig(cam_id=f"cam{i}", kind="file", target=str(fx/f"cam{i}.mp4"), realtime=False) for i in (0,1)])
store = Store(tmp/"p.db"); pl = Pipeline(cfg, store, tmp, save_clips=False)
sid = store.create_session("d"); pl.set_session(sid); pl.start()
t0=time.time()
while time.time()-t0<200 and not pl.is_finished(): time.sleep(0.2)
pl.stop()
truth = sorted(json.load(open(fx/"shots.json")), key=lambda t:t["t_launch"])
for s in sorted(store.list_shots(sid), key=lambda s:s.t_launch)[:int(sys.argv[2])]:
    p=s.track.points
    print(s.shot_id, s.result.value, "t0=%.3f t1=%.3f n=%d"%(p[0].t,p[-1].t,len(p)), "first", [round(v,1) for v in (p[0].x,p[0].y,p[0].z)], "last", [round(v,1) for v in (p[-1].x,p[-1].y,p[-1].z)], s.notes)
print("fin log", pl.finalize_log[:3])
store.close()

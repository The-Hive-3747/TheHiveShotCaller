import json, sys, time, tempfile
from pathlib import Path
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker")
from hiveshot import config as cfgmod
from hiveshot.pipeline import Pipeline
from hiveshot.store import Store
fx = Path(sys.argv[1]); tmp = Path(tempfile.mkdtemp(prefix="refute_"))
cfg = cfgmod.AppConfig(sources=[cfgmod.SourceConfig(cam_id=f"cam{i}", kind="file", target=str(fx/f"cam{i}.mp4"), realtime=False) for i in (0,1)])
store = Store(tmp/"p.db"); pl = Pipeline(cfg, store, tmp, save_clips=False)
sid = store.create_session("d"); pl.set_session(sid)
orig = pl._add_closed
def hook(cam, tracks, t_closed):
    for t in tracks:
        ds=t.detections
        print("closed", cam, "n=%d t=%.2f-%.2f"%(len(ds), ds[0].t, ds[-1].t), "u,v first (%.0f,%.0f) last (%.0f,%.0f)"%(ds[0].u,ds[0].v,ds[-1].u,ds[-1].v))
    return orig(cam, tracks, t_closed)
pl._add_closed = hook
pl.start(); t0=time.time()
while time.time()-t0<200 and not pl.is_finished(): time.sleep(0.2)
pl.stop()
print("last_error", pl.last_error, "shots", len(store.list_shots(sid)))
print([ (round(r['t_last_point'],2), r['fragments']) for r in pl.finalize_log])
print(pl.status().get("warnings"))

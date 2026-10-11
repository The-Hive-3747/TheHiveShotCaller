"""In-process Pipeline run (realtime per RT env) with DEBUG logging, counting events. usage: dod2_3_2_inproc.py <fixture> <out_prefix>"""
import json, os, sys, time, tempfile, logging, collections
from pathlib import Path
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker")
from hiveshot import config as cfgmod
from hiveshot.pipeline import Pipeline
from hiveshot.store import Store
fx = Path(sys.argv[1]); pre = Path(sys.argv[2]); rt = bool(int(os.environ.get("RT", "1")))
class H(logging.Handler):
    def __init__(s): super().__init__(); s.recs = []
    def emit(s, r): s.recs.append((r.created, r.name, r.levelname, r.getMessage()))
h = H(); root = logging.getLogger(); root.setLevel(logging.DEBUG); root.addHandler(h)
tmp = Path(tempfile.mkdtemp(prefix="r2inp_"))
cfg = cfgmod.AppConfig(calibration_path=str(tmp / "calibration.json"), sources=[cfgmod.SourceConfig(cam_id=f"cam{i}", kind="file", target=str(fx / f"cam{i}.mp4"), realtime=rt) for i in (0, 1)])
store = Store(tmp / "p.db"); pl = Pipeline(cfg, store, tmp, save_clips=False)
pl.reload_calibration(); sid = store.create_session("x"); pl.set_session(sid)
t0 = time.time(); pl.start()
try:
    while time.time() - t0 < 200 and not pl.is_finished(): time.sleep(0.2)
finally:
    pl.stop()
st = pl.status()
out = {"elapsed": time.time() - t0, "shots": len(store.list_shots(sid)), "unpaired": getattr(pl, "_unpaired", None),
       "last_error": pl.last_error, "cams": {c: (v["frames_read"], v["dropped"]) for c, v in st["cameras"].items()},
       "timing": st["timing"], "warnings": st["warnings"], "finalize_log_n": len(pl.finalize_log),
       "log_counts": dict(collections.Counter(f"{r[2]} {r[3][:70]}" for r in h.recs if r[1].startswith("hiveshot"))),
       "log_tail": [f"{r[2]} {r[1]} {r[3][:200]}" for r in h.recs if r[1].startswith("hiveshot")][:60]}
Path(str(pre) + ".json").write_text(json.dumps(out, indent=1, default=str))
print(json.dumps({k: out[k] for k in ("elapsed", "shots", "unpaired", "last_error", "cams", "warnings", "finalize_log_n")}, default=str))
for k, v in out["log_counts"].items(): print(v, k)
store.close()

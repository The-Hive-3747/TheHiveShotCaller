"""In-process Pipeline run (realtime per RT env) with instrumentation. usage: dod2_3_2_inproc.py <fixture> <out_prefix>
env: HS_ROOT = code root under test (default repo), RT=1|0"""
import collections, json, logging, os, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, os.environ.get("HS_ROOT", r"C:\Users\3747h\Documents\HiveShotTracker"))
import hiveshot
from hiveshot import config as cfgmod
from hiveshot.pipeline import Pipeline
from hiveshot.store import Store

print("code under test:", hiveshot.__file__)
fx = Path(sys.argv[1]); pre = Path(sys.argv[2]); rt = bool(int(os.environ.get("RT", "1")))


class H(logging.Handler):
    def __init__(s): super().__init__(); s.recs = []
    def emit(s, r):
        import traceback
        msg = r.getMessage() + ("\n" + "".join(traceback.format_exception(*r.exc_info)) if r.exc_info else "")
        s.recs.append((r.created, r.name, r.levelname, msg))


h = H(); root = logging.getLogger(); root.setLevel(logging.DEBUG); root.addHandler(h)
tmp = Path(tempfile.mkdtemp(prefix="r2inp_"))
cnt = collections.Counter(); closed_log = []; T0 = [time.time()]
_orig_add = Pipeline._add_closed
def _add(self, cam, tracks, t_closed):
    for t in tracks:
        closed_log.append((cam, round(t.detections[0].t, 2), round(t.detections[-1].t, 2), len(t.detections),
                           round(t_closed, 2), round(time.time() - T0[0], 2)))
    cnt["add_closed_tracks"] += len(tracks)
    return _orig_add(self, cam, tracks, t_closed)
Pipeline._add_closed = _add
_orig_ing = Pipeline._ingest_fragment
def _ing(self, frag, closed_t):
    cnt["fragments"] += 1
    return _orig_ing(self, frag, closed_t)
Pipeline._ingest_fragment = _ing
_orig_fin = Pipeline._finalize
def _fin(self, tr3, chain=None):
    cnt["finalize_calls"] += 1
    return _orig_fin(self, tr3, chain)
Pipeline._finalize = _fin
_orig_cyc = Pipeline._recon_cycle
def _cyc(self, final=False):
    cnt["recon_cycles"] += 1
    return _orig_cyc(self, final)
Pipeline._recon_cycle = _cyc

cfg = cfgmod.AppConfig(calibration_path=str(tmp / "calibration.json"), sources=[
    cfgmod.SourceConfig(cam_id=f"cam{i}", kind="file", target=str(fx / f"cam{i}.mp4"), realtime=rt) for i in (0, 1)])
store = Store(tmp / "p.db"); pl = Pipeline(cfg, store, tmp, save_clips=False)
pl.reload_calibration(); sid = store.create_session("x"); pl.set_session(sid)
T0[0] = time.time(); t0 = T0[0]; pl.start()
try:
    while time.time() - t0 < 200 and not pl.is_finished():
        time.sleep(0.2)
finally:
    pl.stop()
st = pl.status()
out = {"counters": dict(cnt), "closed_tracks": closed_log, "elapsed": time.time() - t0, "shots": len(store.list_shots(sid)),
       "unpaired": getattr(pl, "_unpaired", None), "last_error": pl.last_error,
       "cams": {c: (v["frames_read"], v["dropped"]) for c, v in st["cameras"].items()},
       "timing": st["timing"], "warnings": st["warnings"], "finalize_log_n": len(pl.finalize_log),
       "log_counts": dict(collections.Counter(f"{r[2]} {r[3][:70]}" for r in h.recs if r[1].startswith("hiveshot"))),
       "log_head": [f"{r[2]} {r[1]} {r[3][:1500]}" for r in h.recs if r[1].startswith("hiveshot")][:60]}
Path(str(pre) + ".json").write_text(json.dumps(out, indent=1, default=str))
print(json.dumps({k: out[k] for k in ("elapsed", "shots", "unpaired", "last_error", "cams", "counters", "warnings", "finalize_log_n")}, default=str)[:900])
for k, v in out["log_counts"].items():
    print(v, k)
store.close()

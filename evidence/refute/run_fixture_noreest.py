"""Refuter harness: run Pipeline (realtime=bool(int(__import__("os").environ.get("RT","0")))) on a fixture dir; compare to shots.json.
usage: run_fixture.py <fixture_dir> <out_json> [burst_gap]"""
import json, sys, time, tempfile
from pathlib import Path
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker")
from hiveshot import config as cfgmod
import hiveshot.pipeline as _pm; _pm.OFFSET_REESTIMATE_S = 1e9
from hiveshot.pipeline import Pipeline
from hiveshot.store import Store
from hiveshot.stats import compute_stats, stats_to_dict

fx = Path(sys.argv[1]); out = Path(sys.argv[2]); gap = float(sys.argv[3]) if len(sys.argv) > 3 else 1.5
tmp = Path(tempfile.mkdtemp(prefix="refute_"))
cfg = cfgmod.AppConfig(burst_gap_s=gap, sources=[
    cfgmod.SourceConfig(cam_id=f"cam{i}", kind="file", target=str(fx / f"cam{i}.mp4"), realtime=bool(int(__import__("os").environ.get("RT","0"))))
    for i in (0, 1)])
store = Store(tmp / "p.db")
pl = Pipeline(cfg, store, tmp, save_clips=False)
sid = store.create_session("refute"); pl.set_session(sid)
import logging; logging.basicConfig(level=logging.INFO, filename=str(out.with_suffix(".log")), filemode="w")
t0 = time.time(); pl.start()
try:
    while time.time() - t0 < 300 and not pl.is_finished():
        time.sleep(0.2)
    fin = pl.is_finished()
finally:
    pl.stop()
truth = sorted(json.loads((fx / "shots.json").read_text()), key=lambda t: t["t_launch"])
shots = sorted(store.list_shots(sid), key=lambda s: s.t_launch)
# truth burst assignment
def bursts(ts, g):
    res = []; b = 0; idx = 0; last = None
    for t in ts:
        if last is None or t - last > g: b += 1; idx = 0
        idx += 1; last = t; res.append((b, idx))
    return res
tb = bursts([t["t_launch"] for t in truth], gap)
exp_hist = {k: 0 for k in range(1, 6)}
for t, (b, i) in zip(truth, tb):
    if not t["made"]: exp_hist[min(i, 5)] += 1
st = pl.stats(sid)
rows = []
used = set()
for t, (b, i) in zip(truth, tb):
    best = None
    for k, s in enumerate(shots):
        if k in used: continue
        d = abs(s.t_launch - t["t_launch"])
        if best is None or d < best[0]: best = (d, k)
    if best is None or best[0] > 0.5:
        rows.append({"truth": t["shot"], "matched": False}); continue
    used.add(best[1]); s = shots[best[1]]
    rows.append({"truth": t["shot"], "matched": True, "dt_launch": s.t_launch - t["t_launch"],
        "made_truth": t["made"], "result": s.result.value,
        "speed_truth": t["speed_ips"], "speed_meas": s.exit_speed_ips,
        "speed_err_pct": None if s.exit_speed_ips is None else 100*(s.exit_speed_ips/t["speed_ips"]-1),
        "angle_deg": s.launch_angle_deg, "has_parabola": s.parabola is not None,
        "has_drag": s.drag is not None, "burst": (s.burst_id, s.burst_index), "burst_truth": tb[truth.index(t)],
        "ball_type": s.ball_type.value, "notes": s.notes})
extra = [s.shot_id for k, s in enumerate(shots) if k not in used]
res = {"fixture": str(fx), "finished": fin, "n_truth": len(truth), "n_shots": len(shots),
       "truth_made": sum(t["made"] for t in truth), "stats": st, "expected_failure_hist": exp_hist,
       "rows": rows, "extra_shots": extra, "elapsed_s": time.time() - t0, "burst_gap": gap}
out.write_text(json.dumps(res, indent=1, default=str))
print(json.dumps({k: res[k] for k in ("finished","n_truth","n_shots","truth_made","expected_failure_hist","extra_shots","elapsed_s")}, default=str))
print("STATS", json.dumps(st, default=str))
mm = [r for r in rows if r["matched"] and (r["made_truth"] != (r["result"] == "made"))]
print("unmatched truth:", [r["truth"] for r in rows if not r["matched"]])
print("make/miss mismatches:", [(r["truth"], r["made_truth"], r["result"]) for r in mm])
errs = [abs(r["speed_err_pct"]) for r in rows if r.get("speed_err_pct") is not None]
if errs: print("speed err pct: max %.2f mean %.2f n=%d" % (max(errs), sum(errs)/len(errs), len(errs)))
print("no parabola:", [r["truth"] for r in rows if r["matched"] and not r["has_parabola"]], "no drag:", [r["truth"] for r in rows if r["matched"] and not r["has_drag"]])
print("burst mismatches:", [(r["truth"], r["burst"], r["burst_truth"]) for r in rows if r["matched"] and tuple(r["burst"]) != tuple(r["burst_truth"])])
store.close()

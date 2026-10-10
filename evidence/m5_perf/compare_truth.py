"""Run a fixture through the pipeline (lockstep) and compare every shot with shots.json.
usage: python evidence/m5_perf/compare_truth.py synth_20 [--realtime]"""
import json
import logging
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, ".")
from hiveshot import config as cfgmod  # noqa: E402
from hiveshot.pipeline import Pipeline  # noqa: E402
from hiveshot.store import Store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
fx = sys.argv[1] if len(sys.argv) > 1 else "synth_20"
realtime = "--realtime" in sys.argv
tmp = Path(tempfile.mkdtemp())
cfg = cfgmod.AppConfig(sources=[
    cfgmod.SourceConfig(cam_id=f"cam{i}", kind="file", target=f"fixtures/{fx}/cam{i}.mp4",
                        realtime=realtime) for i in (0, 1)])
st = Store(tmp / "p.db")
pl = Pipeline(cfg, st, tmp, save_clips=False)
sid = st.create_session("x")
pl.set_session(sid)
pl.start()
t0 = time.time()
while not pl.is_finished() and time.time() - t0 < 300:
    time.sleep(0.1)
pl.stop()
truth = sorted(json.load(open(f"fixtures/{fx}/shots.json")), key=lambda t: t["t_launch"])
shots = sorted(st.list_shots(sid), key=lambda s: s.t_launch)
print(f"stored {len(shots)} of {len(truth)} truth shots; timing {pl.status()['timing']}")
used = set()
for i, t in enumerate(truth):
    best = min((s for s in shots if s.shot_id not in used),
               key=lambda s: abs(s.t_launch - t["t_launch"]), default=None)
    if best is None or abs(best.t_launch - t["t_launch"]) > 0.2:
        print(f"{i:2d} t={t['t_launch']:6.2f} truth_made={bool(t['made'])!s:5} LOST")
        continue
    used.add(best.shot_id)
    err = (best.exit_speed_ips / t["speed_ips"] - 1) * 100 if best.exit_speed_ips else float("nan")
    print(f"{i:2d} t={t['t_launch']:6.2f} truth_made={bool(t['made'])!s:5} got={best.result.value:10s} "
          f"burst={best.burst_id}/{best.burst_index} speed_err={err:+6.2f}% dt={best.t_launch - t['t_launch']:+.3f} "
          f"notes={best.notes[:60]!r}")
extra = [s for s in shots if s.shot_id not in used]
print("extra stored shots:", [(round(s.t_launch, 2), s.result.value) for s in extra])
st.close()

"""Sampling profiler (sys._current_frames @ 4 ms) of a realtime Pipeline run, per thread.
usage: python evidence/m5_perf/rt_sample.py synth_20 [--noclips] [--preview]"""
import collections, sys, tempfile, threading, time
from pathlib import Path
sys.path.insert(0, ".")
from hiveshot import config as cfgmod
from hiveshot.pipeline import Pipeline
from hiveshot.store import Store
fx = sys.argv[1]
tmp = Path(tempfile.mkdtemp())
cfg = cfgmod.AppConfig(sources=[cfgmod.SourceConfig(cam_id=f"cam{i}", kind="file",
    target=f"fixtures/{fx}/cam{i}.mp4", realtime=True, loop=False) for i in (0, 1)])
st = Store(tmp / "p.db")
pl = Pipeline(cfg, st, tmp, save_clips="--noclips" not in sys.argv)
sid = st.create_session("x"); pl.set_session(sid); pl.start()
if "--preview" in sys.argv:
    for c in ("cam0", "cam1"): pl.preview_client_add(c)
tops = collections.defaultdict(collections.Counter)   # thread -> "func file:line" leaf
cums = collections.defaultdict(collections.Counter)   # thread -> function (any depth in hiveshot)
n = collections.Counter()
stop = False
def sampler():
    me = threading.get_ident()
    while not stop:
        frames = sys._current_frames()
        names = {t.ident: t.name for t in threading.enumerate()}
        for ident, f in frames.items():
            if ident == me: continue
            name = names.get(ident, str(ident))
            if "MainThread" in name: continue
            n[name] += 1
            leaf = f"{f.f_code.co_name} {Path(f.f_code.co_filename).name}:{f.f_lineno}"
            tops[name][leaf] += 1
            seen = set(); g = f
            while g is not None:
                fn = g.f_code.co_filename
                if "HiveShotTracker" in fn and ".venv" not in fn:
                    k = f"{g.f_code.co_name} {Path(fn).name}"
                    if k not in seen: cums[name][k] += 1; seen.add(k)
                g = g.f_back
        time.sleep(0.004)
th = threading.Thread(target=sampler, daemon=True, name="sampler"); th.start()
t0 = time.time()
while not pl.is_finished() and time.time() - t0 < 120: time.sleep(0.5)
s = pl.status(); stop = True; pl.stop()
print("wall", round(time.time()-t0,1), {c: (v["frames_read"], v["dropped"]) for c, v in s["cameras"].items()})
print("timing", s["timing"])
for name in sorted(n):
    print(f"===== thread {name}: {n[name]} samples")
    print(" leaf:");  [print(f"  {c:5d} {k}") for k, c in tops[name].most_common(8)]
    print(" in hiveshot (cumulative):");  [print(f"  {c:5d} {k}") for k, c in cums[name].most_common(12)]

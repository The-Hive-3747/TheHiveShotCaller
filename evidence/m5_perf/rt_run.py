"""Realtime run of a fixture through Pipeline; prints drops, timing, shots vs truth.
usage: python evidence/m5_perf/rt_run.py synth_20 [--preview] [--cprofile]"""
import json, sys, tempfile, time, threading
from pathlib import Path
sys.path.insert(0, ".")
from hiveshot import config as cfgmod
from hiveshot.pipeline import Pipeline
from hiveshot.store import Store

fx = sys.argv[1]
tmp = Path(tempfile.mkdtemp())
cfg = cfgmod.AppConfig(sources=[
    cfgmod.SourceConfig(cam_id=f"cam{i}", kind="file", target=f"fixtures/{fx}/cam{i}.mp4",
                        realtime=True, loop=False) for i in (0, 1)])
st = Store(tmp / "p.db")
pl = Pipeline(cfg, st, tmp, save_clips="--noclips" not in sys.argv)
sid = st.create_session("x"); pl.set_session(sid)
pl.start()
if "--preview" in sys.argv:
    for c in ("cam0", "cam1"): pl.preview_client_add(c)
t0 = time.time(); samples = []
while not pl.is_finished() and time.time() - t0 < 120:
    time.sleep(1.0)
    s = pl.status()
    samples.append(s["timing"])
s = pl.status()
pl.stop()
cams = {c: (v["frames_read"], v["dropped"]) for c, v in s["cameras"].items()}
print("wall", round(time.time() - t0, 1), "cameras (read,dropped)", cams)
mid = samples[len(samples)//2] if samples else {}
print("timing(mid)", mid)
print("timing(final)", s["timing"])
truth = sorted(json.load(open(f"fixtures/{fx}/shots.json")), key=lambda t: t["t_launch"])
shots = sorted(st.list_shots(sid), key=lambda x: x.t_launch)
ok = len(shots) == len(truth) and all((x.result.value == "made") == bool(t["made"]) for x, t in zip(shots, truth))
print("shots", len(shots), "of", len(truth), "made", sum(x.result.value == "made" for x in shots), "truth made", sum(bool(t["made"]) for t in truth), "ALL_CORRECT" if ok else "MISMATCH")

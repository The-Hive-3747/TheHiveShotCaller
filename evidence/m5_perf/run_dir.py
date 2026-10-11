"""Lockstep pipeline run on any fixture directory, per-shot report vs shots.json.
usage: python run_dir.py <dir> [--log]"""
import json, logging, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, ".")
from hiveshot import config as cfgmod
from hiveshot.pipeline import Pipeline
from hiveshot.store import Store
d = Path(sys.argv[1])
if "--log" in sys.argv: logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
tmp = Path(tempfile.mkdtemp())
from hiveshot import calib
from hiveshot.models import CameraExtrinsics, CameraIntrinsics
I, E = [], []
for i in (0, 1):
    tj = json.load(open(d / f"cam{i}_truth.json"))
    I.append(CameraIntrinsics(**{**tj["intrinsics"], "cam_id": f"cam{i}", "dist": tuple(tj["intrinsics"]["dist"])}))
    E.append(CameraExtrinsics(**{**tj["extrinsics"], "cam_id": f"cam{i}", "rvec": tuple(tj["extrinsics"]["rvec"]), "tvec": tuple(tj["extrinsics"]["tvec"])}))
calib.save_calibration(tmp / "cal.json", I, E)
cfg = cfgmod.AppConfig(calibration_path=str(tmp / "cal.json"), sources=[cfgmod.SourceConfig(cam_id=f"cam{i}", kind="file", target=str(d / f"cam{i}.mp4"), realtime=False) for i in (0, 1)])
st = Store(tmp / "p.db"); pl = Pipeline(cfg, st, tmp, save_clips=False)
sid = st.create_session("x"); pl.set_session(sid); pl.start()
t0 = time.time()
while not pl.is_finished() and time.time() - t0 < 200: time.sleep(0.1)
s = pl.status(); pl.stop()
truth = sorted(json.load(open(d / "shots.json")), key=lambda t: t["t_launch"])
shots = sorted(st.list_shots(sid), key=lambda x: x.t_launch)
print("warnings", s["warnings"], "stored", len(shots), "of", len(truth))
for t in truth:
    m = min(shots, key=lambda x: abs(x.t_launch - t["t_launch"]), default=None)
    if m is None or abs(m.t_launch - t["t_launch"]) > 0.3: print(t["shot"], "LOST"); continue
    print(t["shot"], "truth_made", t["made"], "speed", round(t["speed_ips"]), "->", m.result.value, "pts", len(m.track.points) if m.track else 0, "speed_meas", round(m.exit_speed_ips or 0), "notes", repr(m.notes))

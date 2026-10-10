import sys, time, tempfile
from pathlib import Path
sys.path.insert(0, ".")
from hiveshot import config as cfgmod
from hiveshot.pipeline import Pipeline
from hiveshot.store import Store
fx = sys.argv[1] if len(sys.argv) > 1 else "synth_basic"
tmp = Path(tempfile.mkdtemp())
cfg = cfgmod.AppConfig(sources=[cfgmod.SourceConfig(cam_id=f"cam{i}", kind="file", target=f"fixtures/{fx}/cam{i}.mp4", realtime=False) for i in (0, 1)])
st = Store(tmp / "p.db"); pl = Pipeline(cfg, st, tmp, save_clips=False)
sid = st.create_session("x"); pl.set_session(sid); pl.start()
t0 = time.time()
while not pl.is_finished() and time.time() - t0 < 120: time.sleep(0.1)
pl.stop()
for s in st.list_shots(sid):
    p = s.track.points
    zs = [q.z for q in p]
    print(s.shot_id, s.result.value, f"t0={p[0].t:.2f} t1={p[-1].t:.2f} n={len(p)} last=({p[-1].x:.0f},{p[-1].y:.0f},{p[-1].z:.1f}) apex={max(zs):.0f} notes={s.notes!r}")
st.close()

import sys, time, shutil
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker\evidence\refute\dod6_10_2")
import simlib as S
from pathlib import Path
d = Path(r"C:\Users\3747h\AppData\Local\Temp\claude\C--Users-3747h-Documents-HiveShotTracker\386da1de-9207-4304-8c4f-9284e5732d29\scratchpad\spot_timing")
if d.exists(): shutil.rmtree(d)
t0 = time.time(); srv = S.Server(8795, d); api = srv.start(); print("process start -> API answers: %.1f s" % (time.time() - t0))
try:
    for p in ("/api/calib/checkerboard.pdf", "/api/calib/tags.pdf", "/api/calib/tags", "/api/calib/points", "/api/setup/status", "/api/setup/status"):
        c, o, dt = api.call("GET", p); print(p, c, "%.2f s" % dt, o.get("_bytes", ""))
finally:
    srv.stop()

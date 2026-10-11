import sys, json, time
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker\evidence\refute\dod6_10_2")
import simlib as S
from pathlib import Path
SC = Path(r"C:\Users\3747h\AppData\Local\Temp\claude\C--Users-3747h-Documents-HiveShotTracker\386da1de-9207-4304-8c4f-9284e5732d29\scratchpad\d610")
vid = SC / "s1_wizard_default_fx" / "vid"
data = SC / "ui_data"
import shutil
if data.exists(): shutil.rmtree(data)
srv = S.Server(int(sys.argv[1]), data)
api = srv.start()
print("server up", flush=True)
# what the operator has after the wizard step 1 (cameras assigned): device sources replaced by files here
cfg = api.ok("GET", "/api/config")
cfg["sources"] = [{"cam_id": f"cam{i}", "kind": "file", "target": str(vid / f"aud_cam{i}.mp4"), "width": 1920, "height": 1080,
                   "fps_hint": 30, "backend": "auto", "loop": True, "realtime": True} for i in (0, 1)]
api.ok("PUT", "/api/config", cfg)
api.ok("POST", "/api/pipeline/start")
print("pipeline started; sleeping", flush=True)
time.sleep(float(sys.argv[2]) if len(sys.argv) > 2 else 1200)
srv.stop()

import sys, time, json, shutil
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker\evidence\refute\dod6_10_2")
import simlib as S
from pathlib import Path
SC = Path(r"C:\Users\3747h\AppData\Local\Temp\claude\C--Users-3747h-Documents-HiveShotTracker\386da1de-9207-4304-8c4f-9284e5732d29\scratchpad\d610")
vid = SC / "s3_click_n2" / "vid"
data = SC / "spot_data"
if data.exists(): shutil.rmtree(data)
srv = S.Server(8795, data); api = srv.start()
try:
    cfg = api.ok("GET", "/api/config")
    cfg["sources"] = [{"cam_id": f"cam{i}", "kind": "file", "target": str(vid / f"aud_cam{i}.mp4"), "width": 1920, "height": 1080,
                       "fps_hint": 30, "backend": "auto", "loop": True, "realtime": True} for i in (0, 1)]
    api.ok("PUT", "/api/config", cfg); api.ok("POST", "/api/pipeline/start"); time.sleep(2)
    r = api.ok("POST", "/api/calib/auto_all", {"source": "kit"})
    t0 = time.time(); seen = []
    while time.time() - t0 < 25:
        st = api.ok("GET", "/api/pipeline/status")
        seen.append((round(time.time() - t0, 1), st["hive_state_source"], st["hive_state"]))
        if st["hive_state_source"] == "tags": break
        time.sleep(1)
    print(json.dumps(seen)); print("warnings", st["warnings"])
    # now simulate the HIVE tipping: far-up video; check whether state/tips follow
    cfg = api.ok("GET", "/api/config"); api.ok("POST", "/api/pipeline/stop")
    cfg["sources"] = [dict(s, target=s["target"].replace("aud_", "far_")) for s in cfg["sources"]]
    api.ok("PUT", "/api/config", cfg); api.ok("POST", "/api/pipeline/start"); time.sleep(10)
    st = api.ok("GET", "/api/pipeline/status"); print("far-up video:", st["hive_state_source"], st["hive_state"], st["warnings"])
finally:
    srv.stop()

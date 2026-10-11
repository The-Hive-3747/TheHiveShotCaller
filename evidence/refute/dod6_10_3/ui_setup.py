import sys, json, time
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker\evidence\refute\dod6_10_3")
from hs3 import Api
SCR = "C:/Users/3747h/AppData/Local/Temp/claude/C--Users-3747h-Documents-HiveShotTracker/386da1de-9207-4304-8c4f-9284e5732d29/scratchpad/d3"
api = Api(8796)
api.call("POST", "/api/pipeline/stop")
cfg = api.ok("GET", "/api/config")
cfg["sources"] = [dict(cam_id=f"cam{i}", kind="file", target=f"{SCR}/A/vid/aud_cam{i}.mp4", width=1920, height=1080, fps_hint=30, backend="auto", loop=True, realtime=True) for i in (0, 1)]
print(api.call("PUT", "/api/config", cfg)[0])
print(api.call("POST", "/api/pipeline/start")[0])
time.sleep(4)
st = api.ok("GET", "/api/pipeline/status")
print(st["running"], st["calibration_loaded"], st["intrinsics_default"], st["warnings"])

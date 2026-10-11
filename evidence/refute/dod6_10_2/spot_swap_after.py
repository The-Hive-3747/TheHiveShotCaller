import sys, time, json, shutil
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker\evidence\refute\dod6_10_2")
import simlib as S
from pathlib import Path
SC = Path(r"C:\Users\3747h\AppData\Local\Temp\claude\C--Users-3747h-Documents-HiveShotTracker\386da1de-9207-4304-8c4f-9284e5732d29\scratchpad\d610")
vid = SC / "s3_click_n2" / "vid"
data = SC / "spot_data2"
if data.exists(): shutil.rmtree(data)
srv = S.Server(8795, data); api = srv.start()
def src(a, b):
    return [{"cam_id": "cam0", "kind": "file", "target": str(vid / f"aud_cam{a}.mp4"), "width": 1920, "height": 1080, "fps_hint": 30, "backend": "auto", "loop": True, "realtime": True},
            {"cam_id": "cam1", "kind": "file", "target": str(vid / f"aud_cam{b}.mp4"), "width": 1920, "height": 1080, "fps_hint": 30, "backend": "auto", "loop": True, "realtime": True}]
try:
    cfg = api.ok("GET", "/api/config"); cfg["sources"] = src(0, 1)
    api.ok("PUT", "/api/config", cfg); api.ok("POST", "/api/pipeline/start"); time.sleep(2)
    r = api.ok("POST", "/api/calib/auto_all", {"source": "kit"}); print("calibrated, xcheck", r["max_error_in"])
    api.ok("POST", "/api/pipeline/stop")
    cfg = api.ok("GET", "/api/config"); cfg["sources"] = src(1, 0)    # operator re-plugs / indexes shuffle: cam0 now shows B's view
    api.ok("PUT", "/api/config", cfg); api.ok("POST", "/api/pipeline/start"); time.sleep(6)
    st = api.ok("GET", "/api/pipeline/status"); ss = api.ok("GET", "/api/setup/status")
    print("after swap: loaded", st["calibration_loaded"], "warnings", st["warnings"], "recs", ss["recommendations"], "mismatch", st["calibration_mismatch"])
    code, cc, dt = api.call("POST", "/api/calib/crosscheck"); print("crosscheck after swap:", code, cc.get("max_error_in"), cc.get("within_1_in"), cc.get("held_out"), cc.get("detail"))
    truth = S.truth_cams("usb", fx=771.0)
    swapped = [truth[1], truth[0]]
    for c, n in zip(swapped, ("cam0", "cam1")):
        pass
    # truth for accuracy: app cam0 now physically shows rig B etc. Compute error of app calibration vs the physical cameras behind the names
    import copy
    from hiveshot.models import CameraIntrinsics, CameraExtrinsics
    phys = []
    for name, tc in (("cam0", truth[1]), ("cam1", truth[0])):
        i = tc.intr
        phys.append(S.synth.VirtualCamera(CameraIntrinsics(name, i.width, i.height, i.fx, i.fy, i.cx, i.cy, i.dist), CameraExtrinsics(name, tc.extr.rvec, tc.extr.tvec)))
    a = S.accuracy(api, phys)
    print("accuracy vs physical:", {k: a[k] for k in ("trajectory", "cell_opening_center_err_in")})
    # re-run auto calibrate (what a user pressing Auto-calibrate again would do)
    r = api.ok("POST", "/api/calib/auto_all", {"source": "kit"}); print("recalibrated xcheck", r["max_error_in"])
    a = S.accuracy(api, phys); print("accuracy after recal:", a["trajectory"]["p95_in"])
finally:
    srv.stop()

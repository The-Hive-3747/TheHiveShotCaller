"""After a lens redo the extrinsics are stale: does /api/setup/finish refuse until Auto-calibrate is run again?"""
import sys, json, time, shutil
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker\evidence\refute\dod6_10_4")
import rig4 as G
from rig4 import *
G.NAME = "t8_stale_finish"
src = SCR / "lens"; work = SCR / "t8"
if work.exists(): shutil.rmtree(work)
shutil.copytree(src / "data", work / "data")
truth = S.truth_cams("usb", fx=800.0, dist=(-0.12, 0.03, 0, 0, 0))
aud = {c: str(src / "vid" / f"aud_{c}.mp4") for c in ("cam0", "cam1")}
bd = SCR / "boards_dist"
srv = Server4(8797, work / "data", mode="exe", cwd=work / "cwd"); api = srv.start()
try:
    set_sources(api, srcs(aud))
    c, r, dt = timed(api, "POST", "/api/setup/finish"); put("0_before", fin_brief(c, r))
    L = lens(api, truth, work, aud, {"cam0": str(bd / "board_near_cam0.mp4"), "cam1": str(bd / "board_near_cam1.mp4")}, cams=("cam0",))
    put("lens", {c: v["out"] for c, v in L.items()})
    put("status", status_brief(api))
    c, r, dt = timed(api, "POST", "/api/setup/finish"); put("finish_with_stale_cam0", fin_brief(c, r))
    put("calib", calib_brief(api)); put("acc", accuracy(api, truth))
finally:
    srv.stop()

"""poor lens -> kit auto_all -> finish 409 -> operator redoes ONLY the lens (good) -> finish again (skipping step 3)"""
import sys, json, time, shutil
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker\evidence\refute\dod6_10_4")
import rig4 as G
from rig4 import *
G.NAME = "t9_poor_then_redo"
src = SCR / "lens"; work = SCR / "t9"
if work.exists(): shutil.rmtree(work)
(work / "data").mkdir(parents=True)
truth = S.truth_cams("usb", fx=800.0, dist=(-0.12, 0.03, 0, 0, 0))
aud = {c: str(src / "vid" / f"aud_{c}.mp4") for c in ("cam0", "cam1")}
bd = SCR / "boards_dist"
far = {c: str(bd / f"board_far_{c}.mp4") for c in ("cam0", "cam1")}; near = {c: str(bd / f"board_near_{c}.mp4") for c in ("cam0", "cam1")}
srv = Server4(8797, work / "data", mode="exe", cwd=work / "cwd"); api = srv.start()
try:
    first_apply(api, srcs(aud))
    L = lens(api, truth, work, aud, far); put("far", {c: (v["out"].get("reprojection_rmse_px"), v["out"].get("intrinsics_source")) for c, v in L.items()})
    c, r, dt = timed(api, "POST", "/api/calib/auto_all", {"source": "kit"}); put("auto_all", dict(code=c, ok=r.get("ok"), max=r.get("max_error_in")))
    put("acc_poor", accuracy(api, truth))
    c, r, dt = timed(api, "POST", "/api/setup/finish"); put("finish_poor", fin_brief(c, r))
    L = lens(api, truth, work, aud, near); put("near", {c: (v["out"].get("reprojection_rmse_px"), v["out"].get("intrinsics_source")) for c, v in L.items()})
    put("status_after_lens_redo", status_brief(api)); put("calib_stale", calib_brief(api)["stale"])
    c, r, dt = timed(api, "POST", "/api/setup/finish"); put("finish_after_lens_only", fin_brief(c, r))
    put("acc_after_lens_only", accuracy(api, truth))
finally:
    srv.stop()

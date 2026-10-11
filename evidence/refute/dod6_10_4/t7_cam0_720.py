"""Model R: the camera that cannot read stickers (cam0) delivers 720p / a 10% zoom after a good calibration: what do auto_all and finish do?"""
import sys, json, time, shutil
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker\evidence\refute\dod6_10_4")
import rig4 as G
from rig4 import *
G.NAME = "t7_cam0_720"
src = SCR / "insample_R"
work = SCR / "t7"
if work.exists(): shutil.rmtree(work)
shutil.copytree(src / "data", work / "data")
truth = S.truth_cams("usb", fx=None)
aud = {c: str(src / "vid" / f"aud_{c}.mp4") for c in ("cam0", "cam1")}
p720, _ = scene(work, truth, "c0_720", "R", size_override={"cam0": (1280, 720)})
zt = S.truth_cams("usb", fx=None)
from hiveshot import synth
from hiveshot.models import CameraIntrinsics
i0 = zt[0].intr
z0 = synth.VirtualCamera(CameraIntrinsics("cam0", i0.width, i0.height, i0.fx * 1.10, i0.fy * 1.10, i0.cx, i0.cy, (0,0,0,0,0)), zt[0].extr)
pz, _ = scene(work, [z0, zt[1]], "c0_zoom", "R")
srv = Server4(8797, work / "data", mode="exe", cwd=work / "cwd"); api = srv.start()
def ack(r):
    ws = list(r.get("warnings") or []) + ([r["warning"]] if r.get("warning") else [])
    return (r.get("out_of_sample") is False) or any("in-sample" in str(w).lower() for w in ws)
try:
    first_apply(api, srcs(aud))
    c, r, dt = timed(api, "POST", "/api/calib/auto_all", {"source": "kit"}); put("0_base", dict(code=c, ok=r.get("ok")))
    c, r, dt = timed(api, "POST", "/api/setup/finish"); put("0_base_finish", dict(fin_brief(c, r), ack=ack(r)))
    for nm, paths in (("cam0_720p", p720), ("cam0_zoom10", pz)):
        set_sources(api, srcs(paths))
        e = {}
        c, r, dt = timed(api, "POST", "/api/calib/auto_all", {"source": "kit"}); e["auto_all"] = dict(code=c, **summ(r))
        e["status"] = status_brief(api)
        c, r, dt = timed(api, "POST", "/api/setup/finish"); e["finish"] = dict(fin_brief(c, r), ack=(ack(r) if c == 200 else None))
        c, r, dt = timed(api, "POST", "/api/calib/crosscheck"); e["crosscheck"] = dict(code=c, max_error_in=r.get("max_error_in"), out_of_sample=r.get("out_of_sample"), warning=r.get("warning"), detail=r.get("detail"))
        put(nm, e)
        set_sources(api, srcs(aud))
        timed(api, "POST", "/api/calib/auto_all", {"source": "kit"})
finally:
    srv.stop()

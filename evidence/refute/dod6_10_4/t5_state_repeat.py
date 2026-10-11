"""Repeat cross-check under different pipeline HIVE states on ONE stored calibration: is the held-out tag set state dependent?"""
import sys, json, time, shutil
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker\evidence\refute\dod6_10_4")
import rig4 as G
from rig4 import *
G.NAME = "t5_state_repeat"
src = SCR / "learn_E"
work = SCR / "t5"
if work.exists(): shutil.rmtree(work)
shutil.copytree(src / "data", work / "data")
aud = {c: str(src / "vid" / f"aud_{c}.mp4") for c in ("cam0", "cam1")}
srv = Server4(8796, work / "data", mode="exe", cwd=work / "cwd"); api = srv.start()
try:
    set_sources(api, srcs(aud))
    out = []
    order = ["red_audience", "blue_far", "red_far", "red_audience", "red_far", "blue_far", "red_far", "red_audience"]
    st = {"red_audience": ("red", "audience"), "blue_far": ("blue", "far"), "red_far": ("red", "far")}
    for nm in order:
        a, u = st[nm]
        api.call("POST", "/api/hive/state", {"alliance": a, "up_cell": u})
        for rep in range(2):
            c, r, dt = timed(api, "POST", "/api/calib/crosscheck")
            out.append((nm, rep, round(r.get("max_error_in", -1), 3), sorted({p["name"].split(" corner")[0].replace("hive tag ", "") for p in r.get("points", [])}, key=int)))
    for o in out: print(o)
    put("rows", out)
finally:
    srv.stop()

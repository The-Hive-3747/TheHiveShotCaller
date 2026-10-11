"""(2) Lens quality: board at 2-5 ft (poor) vs 1.5-3 ft; distorted lens fx 800.  usage: run4_lens.py <port> [exe|src]"""
import sys, shutil, time
from pathlib import Path
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker\evidence\refute\dod6_10_4")
import rig4 as G
from rig4 import *
port = int(sys.argv[1]); mode = sys.argv[2] if len(sys.argv) > 2 else "exe"
G.NAME = "lens"
work = SCR / "lens"
if work.exists(): shutil.rmtree(work)
(work / "data").mkdir(parents=True)
DIST = (-0.12, 0.03, 0, 0, 0)
truth = S.truth_cams("usb", fx=800.0, dist=DIST)
aud, ids = scene(work, truth, "aud", "R")
put("truth", dict(fx=800.0, dist=DIST))
bd = SCR / "boards_dist"; bd.mkdir(exist_ok=True)
def board(label, rng, cams=("cam0", "cam1")):
    out = {}
    for cam in truth:
        if cam.cam_id not in cams: continue
        p = bd / f"board_{label}_{cam.cam_id}.mp4"
        if not p.exists():
            sim3.make_board_video3(p, cam, seconds=25, seed=11 + int(cam.cam_id[-1]), depth_range=rng)
        out[cam.cam_id] = str(p)
    return out
t0 = time.time()
b_far = board("far", (24, 60)); b_near = board("near", (18, 36)); b_mid = board("mid", (30, 48), cams=("cam0",))
put("board_render_s", round(time.time() - t0, 1))
srv = Server4(port, work / "data", mode=mode, cwd=work / "cwd")
api = srv.start()
def lens_rec(L):
    return {c: dict(code=v["stop_code"], rmse=v["out"].get("reprojection_rmse_px"), frames=v["out"].get("frames_used"), src=v["out"].get("intrinsics_source"),
                    warning=v["out"].get("warning"), keys=sorted(v["out"].keys())) for c, v in L.items()}
try:
    first_apply(api, srcs(aud))
    put("0_initial_status", status_brief(api))
    # --- 2a: board at 2-5 ft
    L = lens(api, truth, work, aud, b_far)
    put("2a_far_lens", lens_rec(L))
    st = status_brief(api); put("2a_status", st); put("2a_calib", calib_brief(api))
    c, r, dt = timed(api, "POST", "/api/calib/auto_all", {"source": "kit"})
    put("2a_kit_auto_all", dict(code=c, s=dt, **summ(r))); put("2a_acc", accuracy(api, truth))
    c, r, dt = timed(api, "POST", "/api/setup/finish"); put("2a_finish", fin_brief(c, r))
    put("2a_status_after_kit", status_brief(api))
    # --- persistence of the warning across a restart of the packaged exe
    api.call("POST", "/api/pipeline/stop"); srv.stop(); time.sleep(1.5)
    srv = Server4(port, work / "data", mode=mode, cwd=work / "cwd"); api = srv.start()
    st = api.ok("GET", "/api/pipeline/status"); put("2a_after_restart_warnings", dict(warnings=st["warnings"], isrc={k: v.get("intrinsics_source") for k, v in st["cameras"].items()}))
    first_apply(api, srcs(aud))
    # --- 2b: mid range (cam0 only) to look for the amber band
    L = lens(api, truth, work, aud, b_mid, cams=("cam0",))
    put("2b_mid_cam0", lens_rec(L)); put("2b_status", status_brief(api))
    # --- 2c: board 1.5-3 ft redo (both)
    L = lens(api, truth, work, aud, b_near)
    put("2c_near_lens", lens_rec(L)); put("2c_status", status_brief(api)); put("2c_calib", calib_brief(api))
    c, r, dt = timed(api, "POST", "/api/calib/auto_all", {"source": "kit"})
    put("2c_kit_auto_all", dict(code=c, s=dt, **summ(r))); put("2c_acc", accuracy(api, truth))
    c, r, dt = timed(api, "POST", "/api/setup/finish"); put("2c_finish", fin_brief(c, r))
finally:
    try: api.call("POST", "/api/pipeline/stop")
    except Exception: pass
    srv.stop()
put("api_log", api.log)
print("done lens")

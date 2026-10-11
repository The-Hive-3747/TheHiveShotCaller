"""Scenario B: realistic wide lens (fx 800, barrel distortion). Phase 1: board held 2-5 ft (the old guide range) -> what RMSE,
is it saved, does the wizard let it through. Phase 2: board 1.5-3 ft (current guide) -> RMSE, kit, finish, accuracy.
Docs-realistic mode (only camera B decodes the CELL stickers). usage: run3_B.py <port>"""
import json, shutil, sys, time
from pathlib import Path
import numpy as np
import run3 as B
from run3 import (S, R, put, status_brief, calib_brief, summ, timed, wait_stable, accuracy, srcs_from, set_sources, SCR)
import sim3
from run3_ext import scene_set_mode

B.SC = "B"
port = int(sys.argv[1])
work = SCR / "B"
if work.exists():
    shutil.rmtree(work)
(work / "data").mkdir(parents=True)
DIST = (-0.12, 0.03, 0, 0, 0)
truth = S.truth_cams("usb", fx=800.0, dist=DIST)
put("truth", dict(fx=800.0, dist=DIST))
aud, _ = scene_set_mode(work, truth, "aud", True)
srv = S.Server(port, work / "data")
api = srv.start()


def lens(label, depth_range, cams=("cam0", "cam1")):
    res = {}
    for cam in truth:
        if cam.cam_id not in cams:
            continue
        bpath, vis, npose = sim3.make_board_video3(work / f"board_{label}_{cam.cam_id}.mp4", cam, seconds=25,
                                                   seed=11 + int(cam.cam_id[-1]), depth_range=depth_range)
        s2 = srcs_from(aud)
        for s in s2:
            if s["cam_id"] == cam.cam_id:
                s["target"] = bpath
        set_sources(api, s2)
        api.ok("POST", f"/api/calib/intrinsics/{cam.cam_id}/start")
        time.sleep(21)
        c, o, dt = timed(api, "stop", "POST", f"/api/calib/intrinsics/{cam.cam_id}/stop", timeout=180)
        res[cam.cam_id] = dict(code=c, out=o, s=dt, vis=f"{vis}/{npose}", status=status_brief(api))
    return res


try:
    cfg = api.ok("GET", "/api/config")
    srcs = srcs_from(aud)
    R.apply_sources(api, cfg, [dict(s, cam_id=f"dev{i}") for i, s in enumerate(srcs)], {})
    cfg = api.ok("GET", "/api/config")
    time.sleep(0.8)
    R.apply_sources(api, cfg, srcs, {})
    wait_stable(api)
    L1 = lens("far", (24, 60))
    put("1_lens_far_2to5ft", {c: dict(code=v["code"], out=v["out"], vis=v["vis"], warn=v["status"]["warnings"], isrc={k: x["isrc"] for k, x in v["status"]["cams"].items()}) for c, v in L1.items()})
    set_sources(api, srcs_from(aud))
    c, r, dt = timed(api, "auto", "POST", "/api/calib/auto_all", {"source": "kit"})
    put("1_kit_after_far_lens", dict(code=c, **(summ(r) if c == 200 else {"detail": r})))
    put("1_acc_far_lens", accuracy(api, truth))
    c, r, dt = timed(api, "finish", "POST", "/api/setup/finish")
    put("1_finish_far_lens", dict(code=c, body={k: r.get(k) for k in ("ok", "detail", "max_error_in", "out_of_sample", "warning")}))
    st = api.ok("GET", "/api/calib")
    put("1_fx_saved", {i["cam_id"]: round(i["fx"], 1) for i in st["intrinsics"]})
    # phase 2: redo the lens as the current guide says (1.5 - 3 ft)
    L2 = lens("near", (18, 36))
    put("2_lens_near_1p5to3ft", {c: dict(code=v["code"], out=v["out"], vis=v["vis"], warn=v["status"]["warnings"]) for c, v in L2.items()})
    set_sources(api, srcs_from(aud))
    c, r, dt = timed(api, "auto", "POST", "/api/calib/auto_all", {"source": "kit"})
    put("2_kit_after_near_lens", dict(code=c, **(summ(r) if c == 200 else {"detail": r})))
    put("2_acc_near_lens", accuracy(api, truth))
    c, r, dt = timed(api, "finish", "POST", "/api/setup/finish")
    put("2_finish_near_lens", dict(code=c, body={k: r.get(k) for k in ("ok", "detail", "max_error_in", "out_of_sample", "warning")}))
    st = api.ok("GET", "/api/calib")
    put("2_fx_saved", {i["cam_id"]: round(i["fx"], 1) for i in st["intrinsics"]})
finally:
    try:
        api.call("POST", "/api/pipeline/stop")
    except Exception:
        pass
    srv.stop()
put("api_log", api.log)
print("done B")

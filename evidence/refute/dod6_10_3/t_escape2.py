"""Is the 'both cameras refused' state escapable from the UI-reachable calls? Uses a copy of the deadlocked data dir of
scenario A (extrinsics solved with default intrinsics, then lens measured; both cameras decode HIVE tags)."""
import json, shutil, sys, time
from pathlib import Path
import numpy as np
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "dod6_10_2"))
import simlib as S
import run_s as R
import cv2
cv2.setNumThreads(2)
SCR = Path(r"C:\Users\3747h\AppData\Local\Temp\claude\C--Users-3747h-Documents-HiveShotTracker\386da1de-9207-4304-8c4f-9284e5732d29\scratchpad\d3")
data = SCR / "esc2_data"
if data.exists():
    shutil.rmtree(data)
shutil.copytree(SCR / "E/data", data)
out = {}
srv = S.Server(8797, data)
api = srv.start()
try:
    vids = {"cam0": str(SCR / "E" / "vid" / "moved_cam0.mp4"), "cam1": str(SCR / "E" / "vid" / "moved_cam1.mp4")}
    cfg = api.ok("GET", "/api/config")
    api.call("POST", "/api/pipeline/stop")
    R.apply_sources(api, cfg, R.load_cfg_sources(vids), {})
    R.wait_frames(api)
    time.sleep(2)
    from run3_ext import moved_truth; truth = moved_truth()

    def brief(r):
        if not isinstance(r, dict):
            return r
        if "results" in r:
            return {c: {k: v.get(k) for k in ("ok", "status", "error", "crosscheck_error_in", "oos_error_in", "tags_used", "reprojection_px")} for c, v in r["results"].items()}
        return {k: r.get(k) for k in ("detail", "refused", "crosscheck_error_in", "oos_error_in", "tags_used", "reprojection_px", "source", "warnings")}

    def acc():
        return S.accuracy(api, truth)
    st = api.ok("GET", "/api/pipeline/status")
    out["start_state"] = dict(warnings=st["warnings"], cs=st["calibration_source"])
    a0 = acc()
    out["start_acc_pos_in"] = {c: round(v["pos_err_in"], 2) for c, v in a0["cams"].items()}
    # 1 baseline refusal
    c, r, dt = api.call("POST", "/api/calib/auto_all", {"source": "kit"})
    out["1_auto_all_kit"] = brief(r)
    # 2 no source given (UI-less default path)
    c, r, dt = api.call("POST", "/api/calib/auto_all", {})
    out["2_auto_all_default"] = brief(r)
    # 3 click solve with exact projected points (+0.7 px noise), cam0 then cam1
    pts = api.ok("GET", "/api/calib/points")
    rng = np.random.default_rng(5)
    for cam in truth:
        xyz = np.array([p["xyz"] for p in pts])
        uv = np.c_[cam.project(xyz)] + rng.normal(0, 0.7, (len(pts), 2))
        body = {"points": [{"u": float(u), "v": float(v), "name": p["name"]} for (u, v), p in zip(uv, pts)]}
        c, r, dt = api.call("POST", f"/api/calib/extrinsics/{cam.cam_id}", body)
        out[f"3_click_{cam.cam_id}"] = dict(code=c, **brief(r))
    # 4 HIVE-tags-only solve (wizard radio: No printer) for cam0, then kit for cam1
    c, r, dt = api.call("POST", "/api/calib/extrinsics/cam0/auto", {"source": "hive"})
    out["4_hive_cam0"] = dict(code=c, **brief(r))
    c, r, dt = api.call("POST", "/api/calib/extrinsics/cam1/auto", {"source": "kit"})
    out["4_kit_cam1_after"] = dict(code=c, **brief(r))
    c, r, dt = api.call("POST", "/api/calib/extrinsics/cam0/auto", {"source": "kit"})
    out["4_kit_cam0_after"] = dict(code=c, **brief(r))
    a1 = acc()
    out["end_acc_pos_in"] = {c: round(v["pos_err_in"], 2) for c, v in a1["cams"].items()}
    c, r, dt = api.call("POST", "/api/setup/finish")
    out["end_finish"] = dict(code=c, detail=(r.get("detail") if isinstance(r, dict) else r), max_error_in=r.get("max_error_in") if isinstance(r, dict) else None)
    # 5 both with source both / hive via auto_all
    c, r, dt = api.call("POST", "/api/calib/auto_all", {"source": "hive"})
    out["5_auto_all_hive"] = brief(r)
    c, r, dt = api.call("POST", "/api/calib/auto_all", {"source": "kit"})
    out["6_auto_all_kit_after_hive"] = brief(r)
    a2 = acc()
    out["final_acc_pos_in"] = {c: round(v["pos_err_in"], 2) for c, v in a2["cams"].items()}
finally:
    try:
        api.call("POST", "/api/pipeline/stop")
    except Exception:
        pass
    srv.stop()
(HERE / "results_escape2.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
print(json.dumps(out, indent=1, default=str)[:6000])

# --- last resort: delete calibration.json by hand (not in any guide), restart, re-run Auto-calibrate all
cal = data / "calibration.json"
print("calibration.json exists:", cal.exists())
cal.unlink()
srv = S.Server(8797, data)
api = srv.start()
try:
    cfg = api.ok("GET", "/api/config")
    api.call("POST", "/api/pipeline/stop")
    R.apply_sources(api, cfg, R.load_cfg_sources(vids), {})
    R.wait_frames(api)
    time.sleep(2)
    c, r, dt = api.call("POST", "/api/calib/auto_all", {"source": "kit"})
    res = {k: {kk: v.get(kk) for kk in ("ok", "status", "error", "reprojection_px", "intrinsics_default")} for k, v in r["results"].items()}
    st = api.ok("GET", "/api/pipeline/status")
    print("after deleting calibration.json:", json.dumps(res, default=str)[:900], st["warnings"])
finally:
    try:
        api.call("POST", "/api/pipeline/stop")
    except Exception:
        pass
    srv.stop()

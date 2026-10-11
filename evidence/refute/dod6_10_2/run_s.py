"""Scenario runner: follow the wizard / calibration.md through the real HTTP API.

usage: run_s.py <scenario> [port]
Writes results_<scenario>.json next to this file; videos + data dir go to the scratchpad.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import simlib as S  # noqa: E402

SCR = Path(r"C:\Users\3747h\AppData\Local\Temp\claude\C--Users-3747h-Documents-HiveShotTracker\386da1de-9207-4304-8c4f-9284e5732d29\scratchpad\d610")
HERE = Path(__file__).parent

# name -> parameters
SCEN = {
    # truth lens equals the app's shipped default intrinsics (fx 771, no distortion): best case
    "s1_wizard_default_fx": dict(fx=771.0),
    # truth lens as placement.recommend("usb") assumes (95 deg HFOV, fx 880), wizard only (no intrinsics step)
    "s1b_wizard_fx880": dict(fx=None),
    # as s1b but follow docs/calibration.md section 2 (checkerboard) before auto-calibrate
    "s1c_doc_intrinsics_fx880": dict(fx=None, intr="board"),
    # realistic wide lens: fx 800 and barrel distortion, wizard only
    "s1d_wizard_distorted": dict(fx=800.0, dist=(-0.12, 0.03, 0, 0, 0)),
    "s1e_doc_intrinsics_distorted": dict(fx=800.0, dist=(-0.12, 0.03, 0, 0, 0), intr="board"),
    "s2_hive_only": dict(fx=771.0, source="hive"),
    "s2b_hive_only_fx880": dict(fx=None, source="hive"),
    "s3_click_n1": dict(fx=771.0, flow="click", click_noise=1.0),
    "s3_click_n05": dict(fx=771.0, flow="click", click_noise=0.5),
    "s3_click_n2": dict(fx=771.0, flow="click", click_noise=2.0),
    "s3_click_n3": dict(fx=771.0, flow="click", click_noise=3.0),
    "a1_missing_tag100": dict(fx=771.0, kit_ids=(101, 102, 103)),
    "a1b_missing_tag102": dict(fx=771.0, kit_ids=(100, 101, 103)),
    "a1c_missing_two": dict(fx=771.0, kit_ids=(100, 103)),
    "a2_tape_off_1in_x": dict(fx=771.0, tape_off={100: (1.0, 0.0)}),
    "a2b_tape_off_1in_all_dz": dict(fx=771.0, tape_off={100: (0, -1.0), 101: (0, -1.0), 102: (0, -1.0), 103: (0, -1.0)}),
    "a2c_tape_off_1in_one_z": dict(fx=771.0, tape_off={102: (0, -1.0)}),
    "a2d_tape_off_2in_one_x": dict(fx=771.0, tape_off={101: (-2.0, 0)}),
    "a2e_base_tilt_3deg": dict(fx=771.0, tilt_off={102: 3.0, 103: 3.0}),
    "a2f_base_tilt_10deg_one": dict(fx=771.0, tilt_off={102: 10.0}),
    "a2g_tape_off_05in_all": dict(fx=771.0, tape_off={100: (0.5, 0), 101: (-0.5, 0), 102: (0.5, 0.5), 103: (-0.5, -0.5)}),
    "a3_zoom10": dict(fx=771.0 * 1.1, intr_assumed="default"),
    "a3b_res720_cam1": dict(fx=771.0, size_override={"cam1": (1280, 720)}),
    "a4_swap": dict(fx=771.0, swap=True),
}


def load_cfg_sources(paths, size=(1920, 1080), fps=30, names=("cam0", "cam1")):
    return [{"cam_id": n, "kind": "file", "target": paths[n], "width": size[0], "height": size[1],
             "fps_hint": fps, "backend": "auto", "loop": True, "realtime": True} for n in names]


def apply_sources(api, cfg, sources, rec):
    """UI applySources(): stop, PUT merged config, start."""
    t0 = time.time()
    api.call("POST", "/api/pipeline/stop")
    merged = json.loads(json.dumps(cfg))
    merged["sources"] = sources
    code, new, _ = api.call("PUT", "/api/config", merged)
    assert code == 200, new
    api.ok("POST", "/api/pipeline/start")
    rec["t_apply"] = rec.get("t_apply", 0) + time.time() - t0
    return new


def wait_frames(api, cams=("cam0", "cam1"), timeout=20):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = api.ok("GET", "/api/pipeline/status")
        if all(st["cameras"].get(c, {}).get("frames_read", 0) > 5 for c in cams):
            return st
        time.sleep(0.3)
    return api.ok("GET", "/api/pipeline/status")


def summarize_auto(r):
    out = {"ok": r.get("ok"), "max_error_in": r.get("max_error_in"), "per_cam": {}}
    for c, v in (r.get("results") or {}).items():
        out["per_cam"][c] = {k: v.get(k) for k in ("ok", "rmse_in", "tags_used", "tags_missing", "reprojection_px",
                                                  "max_corner_px", "warnings", "error", "status")}
    cc = r.get("crosscheck")
    if cc:
        out["crosscheck"] = {k: cc.get(k) for k in ("max_error_in", "within_1_in", "error", "out_of_sample", "held_out", "warning")}
        if cc.get("points"):
            out["crosscheck"]["n_points"] = len(cc["points"])
    return out


def run(name, port=8793):
    P = dict(SCEN[name])
    work = SCR / name
    if work.exists():
        shutil.rmtree(work)
    (work / "data").mkdir(parents=True)
    import glob, os
    stamp = max(os.path.getmtime(f) for f in glob.glob(str(S.ROOT / "hiveshot" / "*.py")) + glob.glob(str(S.ROOT / "ui" / "*")))
    rec = {"src_latest_mtime": time.strftime("%H:%M:%S", time.localtime(stamp)), "scenario": name, "params": {k: (str(v) if not isinstance(v, (int, float, str, type(None))) else v)
                                         for k, v in P.items()}, "steps": {}}
    truth = S.truth_cams("usb", fx=P.get("fx"), dist=P.get("dist", (0, 0, 0, 0, 0)), swap=P.get("swap", False))
    rec["truth_fx"] = truth[0].intr.fx
    kit = P.get("kit_ids", (100, 101, 102, 103))
    ball = np.array([[5.0, 30.0, 30.0]])
    t0 = time.time()
    paths, drawn = S.make_scene_videos(work / "vid", truth, kit, P.get("tape_off"), "audience", "aud",
                                       ball_xyz=ball, size_override=P.get("size_override"), tilt_off=P.get("tilt_off"))
    paths_far, drawn_far = S.make_scene_videos(work / "vid", truth, kit, P.get("tape_off"), "far", "far",
                                               ball_xyz=ball, size_override=P.get("size_override"), tilt_off=P.get("tilt_off"))
    rec["render_s"] = time.time() - t0
    rec["tags_drawn"] = drawn
    srv = S.Server(port, work / "data")
    api = srv.start()
    try:
        rec["steps"] = run_flow(api, P, truth, paths, paths_far, work, rec)
    finally:
        try:
            api.call("POST", "/api/pipeline/stop")
        except Exception:
            pass
        srv.stop()
    rec["api_log"] = api.log
    (HERE / f"results_{name}.json").write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    return rec


def run_flow(api, P, truth, paths, paths_far, work, rec):
    steps = {}

    def T(label):
        steps[label] = {"t0": time.time()}

    def done(label, **kw):
        steps[label]["s"] = round(time.time() - steps[label].pop("t0"), 2)
        steps[label].update(kw)

    sizes = {c.cam_id: (c.intr.width, c.intr.height) for c in truth}
    # ---- UI init: GET config, status, setup/status
    T("init")
    cfg = api.ok("GET", "/api/config")
    st = api.ok("GET", "/api/pipeline/status")
    ss = api.ok("GET", "/api/setup/status")
    done("init", sources_configured=ss["sources_configured"], calibration_loaded=ss["calibration_loaded"],
         warnings=st.get("warnings"), recs=ss["recommendations"], wizard_opens=(ss["sources_configured"] is False
                                                                                  or ss["calibration_loaded"] is False))
    # ---- step 1: cameras. "Detect and preview" then "This is the -X wall camera"
    T("1_cameras")
    srcs = load_cfg_sources(paths, size=(1920, 1080))
    srcs_dev = [dict(s, cam_id=f"dev{i}") for i, s in enumerate(srcs)]
    apply_sources(api, cfg, srcs_dev, steps)
    cfg = api.ok("GET", "/api/config")
    time.sleep(0.8)
    apply_sources(api, cfg, srcs, steps)
    st = wait_frames(api)
    ss = api.ok("GET", "/api/setup/status")
    done("1_cameras", cameras={c: {"frames": v["frames_read"], "props": v["props"]} for c, v in st["cameras"].items()},
         warnings=st.get("warnings"), recs=ss["recommendations"])
    # ---- optional: intrinsics via checkerboard (calibration.md section 2), per camera
    if P.get("intr") == "board":
        T("2_intrinsics_doc")
        res = {}
        api.call("POST", "/api/pipeline/stop")
        cfg = api.ok("GET", "/api/config")
        for cam in truth:
            bpath = S.make_board_video(work / f"board_{cam.cam_id}.mp4", cam, seconds=25, seed=7 + int(cam.cam_id[-1]))
            # camera A's board video as the source for cam0 only; the other one keeps its scene video
            s2 = load_cfg_sources(paths)
            for s in s2:
                if s["cam_id"] == cam.cam_id:
                    s["target"] = bpath
            apply_sources(api, cfg, s2, steps)
            wait_frames(api)
            api.ok("POST", f"/api/calib/intrinsics/{cam.cam_id}/start")
            time.sleep(24)
            code, out, dt = api.call("POST", f"/api/calib/intrinsics/{cam.cam_id}/stop", timeout=180)
            res[cam.cam_id] = {"code": code, **{k: out.get(k) for k in ("reprojection_rmse_px", "frames_used", "detail")},
                               "solve_s": round(dt, 2)}
        apply_sources(api, cfg, srcs, steps)
        wait_frames(api)
        calib = api.ok("GET", "/api/calib")
        res["fx_saved"] = {i["cam_id"]: i["fx"] for i in calib["intrinsics"]}
        res["fx_true"] = {c.cam_id: c.intr.fx for c in truth}
        done("2_intrinsics_doc", **res)
        steps["2_intrinsics_doc"]["note"] = "scene source swapped for the board video per camera = harness artifact; operator time 2 x (25 s wave + ~2 s solve)"

    # ---- step 2: tags
    T("2_tags_pdf")
    code, out, dt = api.call("GET", "/api/calib/tags")
    code2, out2, dt2 = api.call("GET", "/api/calib/tags.pdf")
    done("2_tags_pdf", tags_json_code=code, n_tags=len(out) if isinstance(out, list) else None,
         pdf_code=code2, pdf_bytes=out2.get("_bytes"), pdf_ct=out2.get("_ct"))
    ss = api.ok("GET", "/api/setup/status")
    steps["2_tags_pdf"]["tags_seen"] = ss["tags_seen"]
    steps["2_tags_pdf"]["recs"] = ss["recommendations"]

    flow = P.get("flow", "auto")
    source = P.get("source", "kit")
    if flow == "auto":
        T("2_auto_all")
        code, r, dt = api.call("POST", "/api/calib/auto_all", {"source": source}, timeout=180)
        done("2_auto_all", code=code, **(summarize_auto(r) if code == 200 else {"detail": r}))
        if code != 200:
            return steps
    else:
        # click method (docs section 3B): project the 8 points, add click noise, POST per camera
        T("3b_click")
        pts = api.ok("GET", "/api/calib/points")
        rng = np.random.default_rng(11)
        per = {}
        for cam in truth:
            xyz = np.array([p["xyz"] for p in pts])
            uv = np.c_[cam.project(xyz)] + rng.normal(0, P["click_noise"], (len(pts), 2))
            body = {"points": [{"u": float(u), "v": float(v), "name": p["name"]} for (u, v), p in zip(uv, pts)]}
            code, r, dt = api.call("POST", f"/api/calib/extrinsics/{cam.cam_id}", body)
            per[cam.cam_id] = {"code": code, "rmse_in": r.get("rmse_in"), "detail": r.get("detail"),
                               "max_err_px": max((p["err_px"] for p in r.get("per_point", [])), default=None),
                               "n_over_2px": sum(1 for p in r.get("per_point", []) if p["err_px"] > 2)}
        code, cc, dt = api.call("POST", "/api/calib/crosscheck")
        done("3b_click", per_cam=per, crosscheck={k: cc.get(k) for k in ("max_error_in", "within_1_in", "detail", "out_of_sample", "held_out", "warning")})

    # ---- step 3 (optional): learn HIVE tags in both states
    if P.get("learn", True) and flow == "auto":
        T("3_learn")
        lr = {}
        code, r, dt = api.call("POST", "/api/calib/hive_tags/learn", {"state": {"alliance": "red", "up_cell": "audience"}})
        lr["audience"] = {"code": code, **{k: r.get(k) for k in ("learned_ids", "missing_ids", "max_residual_in",
                                                                  "up_cell_error_in", "detail")}}
        cfg = api.ok("GET", "/api/config")
        apply_sources(api, cfg, load_cfg_sources(paths_far), steps)     # operator tips the HIVE by hand
        wait_frames(api)
        code, r, dt = api.call("POST", "/api/calib/hive_tags/learn", {"state": {"alliance": "red", "up_cell": "far"}})
        lr["far"] = {"code": code, **{k: r.get(k) for k in ("learned_ids", "missing_ids", "max_residual_in",
                                                              "up_cell_error_in", "detail")}}
        cfg = api.ok("GET", "/api/config")
        apply_sources(api, cfg, srcs, steps)
        wait_frames(api)
        done("3_learn", **lr)

    # ---- step 4: colours: click the ball in cam0 (2 px click error)
    T("4_colors")
    try:
        uv = np.c_[truth[0].project(np.array([[5.0, 30.0, 30.0]]))][0]
        code, r, dt = api.call("POST", "/api/detector/sample", {"cam_id": "cam0", "u": float(uv[0] + 2), "v": float(uv[1] - 2),
                                                                "ball_type": "pollen"})
        done("4_colors", code=code, **{k: r.get(k) for k in ("sampled_hsv", "range", "detail")}, click=uv.round(1).tolist())
    except Exception as e:  # noqa: BLE001
        done("4_colors", error=str(e))

    # ---- step 5: finish
    T("5_finish")
    st = api.ok("GET", "/api/pipeline/status")
    if not st["running"]:
        api.ok("POST", "/api/pipeline/start")
    r = api.ok("POST", "/api/sessions", {"name": "wizard session"})
    time.sleep(1.5)
    st = api.ok("GET", "/api/pipeline/status")
    ss = api.ok("GET", "/api/setup/status")
    done("5_finish", session=r, running=st["running"], calibration_loaded=st["calibration_loaded"],
         hive_state_source=st.get("hive_state_source"), warnings=st.get("warnings"),
         calibration_mismatch=st.get("calibration_mismatch"), recs=ss["recommendations"],
         tags_seen=ss["tags_seen"])
    # ---- accuracy vs truth (independent of anything the app reports)
    T("accuracy")
    done("accuracy", **S.accuracy(api, truth))
    # explicit crosscheck result for the record
    code, cc, dt = api.call("POST", "/api/calib/crosscheck")
    steps["crosscheck_after"] = {"code": code, **{k: cc.get(k) for k in ("max_error_in", "within_1_in", "detail", "out_of_sample", "held_out", "warning")}}
    code, cc, dt = api.call("POST", "/api/calib/crosscheck", {"in_sample": True})
    steps["crosscheck_in_sample"] = {"code": code, **{k: cc.get(k) for k in ("max_error_in", "within_1_in", "detail", "out_of_sample")}}
    return steps


if __name__ == "__main__":
    name = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8793
    r = run(name, port)
    print(json.dumps(r["steps"], indent=1, default=str)[:6000])

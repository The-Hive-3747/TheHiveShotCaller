"""Round 3 driver. usage: run3.py <scenario> <port>   (scenarios: A, B)"""
import json, os, shutil, sys, time
from pathlib import Path
import numpy as np
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "dod6_10_2"))
import simlib as S
import sim3
import cv2
cv2.setNumThreads(2)
import run_s as R

SCR = Path(r"C:\Users\3747h\AppData\Local\Temp\claude\C--Users-3747h-Documents-HiveShotTracker\386da1de-9207-4304-8c4f-9284e5732d29\scratchpad\d3")
OUT = {}
SC = "X"


def put(k, v):
    OUT[k] = v
    (HERE / f"results_{SC}.json").write_text(json.dumps(OUT, indent=1, default=str), encoding="utf-8")


def status_brief(api):
    st = api.ok("GET", "/api/pipeline/status")
    return dict(running=st["running"], calibration_loaded=st["calibration_loaded"], calibration_source=st["calibration_source"],
                intrinsics_default=st["intrinsics_default"], warnings=st["warnings"],
                mismatch=st.get("calibration_mismatch"),
                cams={k: dict(cs=v.get("calibration_source"), isrc=v.get("intrinsics_source"), frames=v.get("frames_read")) for k, v in st["cameras"].items()})


def calib_brief(api):
    c = api.ok("GET", "/api/calib")
    return dict(keys=list(c.keys()),
                fx={i["cam_id"]: round(i["fx"], 1) for i in c["intrinsics"]},
                rmse={i["cam_id"]: i.get("reprojection_rmse_px") for i in c["intrinsics"]},
                intr_has_source=[("intrinsics_source" in i) for i in c["intrinsics"]],
                top_isrc=c.get("intrinsics_source"),
                stale={e["cam_id"]: e.get("stale") for e in c["extrinsics"]},
                ext_rmse_in={e["cam_id"]: e.get("rmse_in") for e in c["extrinsics"]},
                solve_tags=c.get("solve_tags"), raw_ext={e["cam_id"]: (e["rvec"], e["tvec"]) for e in c["extrinsics"]})


def summ(r):
    out = dict(ok=r.get("ok"), max_error_in=r.get("max_error_in"), per_cam={})
    for c, v in (r.get("results") or {}).items():
        out["per_cam"][c] = {k: v.get(k) for k in ("ok", "status", "refused", "error", "fit_residual_in", "rmse_in", "oos_error_in",
                             "crosscheck_error_in", "tags_used", "tags_missing", "reprojection_px", "intrinsics_default",
                             "frame_size", "intrinsics_size", "warnings")}
    cc = r.get("crosscheck")
    if cc:
        out["crosscheck"] = {k: cc.get(k) for k in ("max_error_in", "within_1_in", "out_of_sample", "held_out", "warning", "error")}
    out["calibration_source"] = r.get("calibration_source")
    return out


def timed(api, label, method, path, body=None, timeout=300):
    code, out, dt = api.call(method, path, body, timeout=timeout)
    return code, out, round(dt, 2)


def wait_stable(api, secs=2.0):
    R.wait_frames(api)
    time.sleep(secs)


def accuracy(api, truth):
    a = S.accuracy(api, truth)
    if "error" in a:
        return a
    return dict(pos_err_in={c: round(v["pos_err_in"], 2) for c, v in a["cams"].items()},
                rot_err_deg={c: round(v["rot_err_deg"], 2) for c, v in a["cams"].items()},
                fx={c: (round(v["fx_app"], 1), round(v["fx_true"], 1)) for c, v in a["cams"].items()},
                traj_mean=round(a["trajectory"]["mean_in"], 2), traj_p95=round(a["trajectory"]["p95_in"], 2),
                traj_max=round(a["trajectory"]["max_in"], 2), cell_center_err=round(a["cell_opening_center_err_in"], 2))


def scene_set(work, truth, tag, **kw):
    ball = np.array([[5.0, 30.0, 30.0]])
    paths, ids = S.make_scene_videos(work / "vid", truth, kw.pop("kit", (100, 101, 102, 103)), kw.pop("tape_off", None),
                                     kw.pop("hive_up", "audience"), tag, ball_xyz=ball, **kw)
    return paths, ids


def srcs_from(paths, size=(1920, 1080)):
    return R.load_cfg_sources(paths, size=size)


def set_sources(api, srcs):
    cfg = api.ok("GET", "/api/config")
    R.apply_sources(api, cfg, srcs, {})
    wait_stable(api)


def lens_step(api, truth, work, cams, depth_range, label, seed0=7):
    """Operator records the board for each cam in sequence (wizard: Start recording / Stop recording)."""
    res = {}
    api.call("POST", "/api/pipeline/stop")
    for cam in truth:
        if cam.cam_id not in cams:
            continue
        cached = SCR / "boards" / f"board_{label}_{cam.cam_id}.mp4"
        if cached.exists():
            bpath, vis, npose = str(cached), -1, -1
        else:
            cached.parent.mkdir(exist_ok=True)
            bpath, vis, npose = sim3.make_board_video3(cached, cam, seconds=25,
                                                       seed=seed0 + int(cam.cam_id[-1]), depth_range=depth_range)
        s2 = srcs_from({c.cam_id: str(work / "vid" / f"aud_{c.cam_id}.mp4") for c in truth})
        for s in s2:
            if s["cam_id"] == cam.cam_id:
                s["target"] = bpath
        set_sources(api, s2)
        c1, o1, d1 = timed(api, "start", "POST", f"/api/calib/intrinsics/{cam.cam_id}/start")
        time.sleep(21)    # operator waves the board ~20 s
        c2, o2, d2 = timed(api, "stop", "POST", f"/api/calib/intrinsics/{cam.cam_id}/stop", timeout=180)
        res[cam.cam_id] = dict(start=c1, stop=c2, stop_s=d2, out=o2, board_poses_visible=f"{vis}/{npose}")
        res[cam.cam_id]["after_status"] = status_brief(api)
        res[cam.cam_id]["after_calib"] = {k: v for k, v in calib_brief(api).items() if k != "raw_ext"}
    return res


def kit_flow(api, truth, tag_prefix=""):
    pass


# --------------------------------------------------------------------------------------------------
def scenario_A(port):
    work = SCR / "A"
    if work.exists():
        shutil.rmtree(work)
    (work / "data").mkdir(parents=True)
    truth = S.truth_cams("usb", fx=None)         # 95 deg lens, fx 880
    put("truth_fx", truth[0].intr.fx)
    t0 = time.time()
    aud, ids_a = scene_set(work, truth, "aud")
    far, _ = scene_set(work, truth, "far", hive_up="far")
    put("tags_drawn", ids_a)
    put("render_scene_s", round(time.time() - t0, 1))
    srv = S.Server(port, work / "data")
    api = srv.start()
    try:
        cfg = api.ok("GET", "/api/config")
        put("0_init", status_brief(api))
        # step 1 as the UI does it
        srcs = srcs_from(aud)
        R.apply_sources(api, cfg, [dict(s, cam_id=f"dev{i}") for i, s in enumerate(srcs)], {})
        cfg = api.ok("GET", "/api/config")
        time.sleep(0.8)
        R.apply_sources(api, cfg, srcs, {})
        wait_stable(api)
        put("1_cameras", status_brief(api))
        put("1_calib_before", {k: v for k, v in calib_brief(api).items() if k != "raw_ext"})

        # ---- TRAP: default intrinsics (fx771) vs true fx 880. API does not stop Auto-calibrate; the UI gate does.
        c, r, dt = timed(api, "auto", "POST", "/api/calib/auto_all", {"source": "kit"})
        put("2_trap_auto_all", dict(code=c, s=dt, **(summ(r) if c == 200 else {"detail": r})))
        put("2_trap_status", status_brief(api))
        put("2_trap_accuracy", accuracy(api, truth))
        c, r, dt = timed(api, "finish", "POST", "/api/setup/finish")
        put("2_trap_finish", dict(code=c, s=dt, body=r))
        c, r, dt = timed(api, "xc", "POST", "/api/calib/crosscheck")
        put("2_trap_crosscheck", dict(code=c, s=dt, max_error_in=r.get("max_error_in"), out_of_sample=r.get("out_of_sample"), held_out=r.get("held_out"), warning=r.get("warning")))

        # ---- LENS STEP (1.5-3 ft, +-30 deg), cam0 then cam1
        t0 = time.time()
        L = lens_step(api, truth, work, {"cam0", "cam1"}, (18, 36), "near")
        put("3_lens", L)
        put("3_lens_total_wall_s", round(time.time() - t0, 1))
        set_sources(api, srcs_from(aud))
        put("3_after_lens_status", status_brief(api))
        put("3_after_lens_calib", {k: v for k, v in calib_brief(api).items() if k != "raw_ext"})
        c, r, dt = timed(api, "finish", "POST", "/api/setup/finish")
        put("3_finish_before_recal", dict(code=c, s=dt, body=r))

        # ---- KIT calibration with measured intrinsics
        c, r, dt = timed(api, "auto", "POST", "/api/calib/auto_all", {"source": "kit"})
        put("4_kit_auto_all", dict(code=c, s=dt, **(summ(r) if c == 200 else {"detail": r})))
        put("4_kit_status", status_brief(api))
        put("4_kit_accuracy", accuracy(api, truth))
        c, r, dt = timed(api, "xc", "POST", "/api/calib/crosscheck")
        put("4_kit_crosscheck", dict(code=c, s=dt, max_error_in=r.get("max_error_in"), out_of_sample=r.get("out_of_sample"), held_out=r.get("held_out"), warning=r.get("warning"),
                                      points=[(p["name"], round(p["error_in"], 2)) for p in r.get("points", [])][:20]))
        c, r, dt = timed(api, "xc", "POST", "/api/calib/crosscheck", {"in_sample": True})
        put("4_kit_crosscheck_insample", dict(code=c, max_error_in=r.get("max_error_in"), out_of_sample=r.get("out_of_sample")))
        for cam in ("cam0", "cam1"):
            c, r, dt = timed(api, "auto1", "POST", f"/api/calib/extrinsics/{cam}/auto", {"source": "kit"})
            put(f"4_kit_single_{cam}", dict(code=c, s=dt, **{k: r.get(k) for k in ("ok", "fit_residual_in", "oos_error_in", "tags_used", "reprojection_px", "warnings", "detail", "refused", "intrinsics_default")}))
        c, r, dt = timed(api, "finish", "POST", "/api/setup/finish")
        put("4_finish", dict(code=c, s=dt, body=r))
        good = calib_brief(api)
        put("4_good_calib_ext", good["raw_ext"])

        # ---- LEARN
        L2 = {}
        set_sources(api, srcs_from(far))
        c, r, dt = timed(api, "learn", "POST", "/api/calib/hive_tags/learn", {"state": {"alliance": "red", "up_cell": "far"}})
        L2["far_first"] = dict(code=c, s=dt, body={k: r.get(k) for k in ("learned", "complete", "learned_ids", "missing_ids", "reason", "visible_per_camera", "detail")})
        set_sources(api, srcs_from(aud))
        c, r, dt = timed(api, "learn", "POST", "/api/calib/hive_tags/learn", {"state": {"alliance": "red", "up_cell": "audience"}})
        L2["audience"] = dict(code=c, s=dt, body={k: r.get(k) for k in ("learned", "complete", "learned_ids", "missing_ids", "max_residual_in", "up_cell_error_in", "visible_per_camera", "detail")})
        set_sources(api, srcs_from(far))
        c, r, dt = timed(api, "learn", "POST", "/api/calib/hive_tags/learn", {"state": {"alliance": "red", "up_cell": "far"}})
        L2["far_after_audience"] = dict(code=c, s=dt, body={k: r.get(k) for k in ("learned", "complete", "learned_ids", "missing_ids", "reason", "visible_per_camera", "detail")})
        put("5_learn", L2)
        set_sources(api, srcs_from(aud))
        time.sleep(4)
        put("5_status_after_learn", dict(hive_state_source=api.ok("GET", "/api/pipeline/status").get("hive_state_source")))

        # ---- SAVE GATES (all on top of the good calibration above)
        G = {}
        paths720, _ = scene_set(work, truth, "r720", size_override={"cam1": (1280, 720)})
        set_sources(api, srcs_from({"cam0": paths720["cam0"], "cam1": paths720["cam1"]}))
        put("6_g1_status", status_brief(api))
        before = calib_brief(api)["raw_ext"]
        c, r, dt = timed(api, "auto", "POST", "/api/calib/auto_all", {"source": "kit"})
        after = calib_brief(api)["raw_ext"]
        G["g1_720p_cam1"] = dict(code=c, s=dt, res=(summ(r) if c == 200 else r),
                                 cam0_changed=before["cam0"] != after["cam0"], cam1_changed=before["cam1"] != after["cam1"])
        c1, r1, _ = timed(api, "single", "POST", "/api/calib/extrinsics/cam1/auto", {"source": "kit"})
        G["g1_single_cam1"] = dict(code=c1, body={k: r1.get(k) for k in ("detail", "refused", "reprojection_px", "frame_size", "intrinsics_size")})
        c2, r2, _ = timed(api, "finish", "POST", "/api/setup/finish")
        G["g1_finish"] = dict(code=c2, body=r2)
        put("6_gates", G)
        set_sources(api, srcs_from(aud))
        c, r, dt = timed(api, "auto", "POST", "/api/calib/auto_all", {"source": "kit"})
        G["g1_restore"] = dict(code=c, res=(summ(r) if c == 200 else r), acc=accuracy(api, truth))
        put("6_gates", G)

        variants = {
            "g2a_one_tag_2in_x": {101: (-2.0, 0.0)},
            "g2b_all_four_2in_mixed": {100: (2.0, 0.0), 101: (-2.0, 0.0), 102: (0.0, 2.0), 103: (2.0, -2.0)},
            "g2c_all_four_1in_low": {100: (0, -1.0), 101: (0, -1.0), 102: (0, -1.0), 103: (0, -1.0)},
            "g2d_one_base_1in_low": {102: (0, -1.0)},
        }
        for name, tape in variants.items():
            gp, _ = scene_set(work, truth, name, tape_off=tape)
            set_sources(api, srcs_from(gp))
            good_before = calib_brief(api)["raw_ext"]
            c, r, dt = timed(api, "auto", "POST", "/api/calib/auto_all", {"source": "kit"})
            now = calib_brief(api)["raw_ext"]
            entry = dict(code=c, s=dt, res=(summ(r) if c == 200 else r),
                         cam0_changed=good_before["cam0"] != now["cam0"], cam1_changed=good_before["cam1"] != now["cam1"],
                         acc_after=accuracy(api, truth))
            c2, r2, _ = timed(api, "finish", "POST", "/api/setup/finish")
            entry["finish"] = dict(code=c2, body=({k: r2.get(k) for k in ("ok", "detail", "max_error_in", "out_of_sample", "calibration_source")} if isinstance(r2, dict) else r2))
            G[name] = entry
            put("6_gates", G)
            set_sources(api, srcs_from(aud))
            c, r, dt = timed(api, "auto", "POST", "/api/calib/auto_all", {"source": "kit"})
            G[name]["restore_code"] = c
            G[name]["restore_acc"] = accuracy(api, truth)
            put("6_gates", G)

        # swap after a good calibration (operator re-plugs cables): cam0 gets B picture and cam1 gets A picture
        swp = {"cam0": aud["cam1"], "cam1": aud["cam0"]}
        set_sources(api, srcs_from(swp))
        S3 = dict(status=status_brief(api))
        c, r, dt = timed(api, "xc", "POST", "/api/calib/crosscheck")
        S3["crosscheck"] = dict(code=c, max_error_in=r.get("max_error_in"), out_of_sample=r.get("out_of_sample"), detail=r.get("detail"), warning=r.get("warning"))
        c, r, dt = timed(api, "finish", "POST", "/api/setup/finish")
        S3["finish"] = dict(code=c, body={k: r.get(k) for k in ("ok", "detail", "max_error_in", "out_of_sample")})
        c, r, dt = timed(api, "auto", "POST", "/api/calib/auto_all", {"source": "kit"})
        S3["auto_all_swapped"] = dict(code=c, res=(summ(r) if c == 200 else r))
        c, r, dt = timed(api, "finish", "POST", "/api/setup/finish")
        S3["finish_after_resolve"] = dict(code=c, body={k: r.get(k) for k in ("ok", "detail", "max_error_in", "out_of_sample")})
        put("7_swap_after_cal", S3)
    finally:
        try:
            api.call("POST", "/api/pipeline/stop")
        except Exception:
            pass
        srv.stop()
    put("api_log", api.log)


if __name__ == "__main__":
    SC = sys.argv[1]
    port = int(sys.argv[2])
    {"A": scenario_A}[SC](port)
    print("done", SC)

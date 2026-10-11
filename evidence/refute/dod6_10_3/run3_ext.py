"""Round 3, scenarios R (docs-realistic: only camera B decodes the CELL stickers, wizard order incl. the lens trap)
and E (both cameras decode the stickers, clean wizard order).  usage: run3_ext.py R|E <port>"""
import json, shutil, sys, time
from pathlib import Path
import numpy as np
import run3 as B
from run3 import (S, R, put, status_brief, calib_brief, summ, timed, wait_stable, accuracy, scene_set, srcs_from, set_sources,
                  lens_step, SCR)


def scene_set_mode(work, truth, tag, real, **kw):
    """real=True: only cam1 (camera B, the tag reader) decodes the CELL stickers; cam0 sees them too obliquely
    (calibration.md says 60 deg off normal): its picture is rendered without HIVE tags. real=False: both decode."""
    if not real:
        return scene_set(work, truth, tag, **kw)
    ball = np.array([[5.0, 30.0, 30.0]])
    kw = dict(kw)
    kit = kw.pop("kit", (100, 101, 102, 103))
    tape = kw.pop("tape_off", None)
    hive_up = kw.pop("hive_up", "audience")
    so = kw.pop("size_override", None)
    p0, _ = S.make_scene_videos(work / "vid", [truth[0]], kit, tape, hive_up, tag, hive_tags=False, ball_xyz=ball, size_override=so)
    p1, ids = S.make_scene_videos(work / "vid", [truth[1]], kit, tape, hive_up, tag, hive_tags=True, ball_xyz=ball, size_override=so)
    return {**p0, **p1}, ids


def moved_truth(fx=None, d0=(5.0, -3.0, 2.0), d1=(-4.0, 4.0, -2.0), aim_jit=(2.0, -2.0)):
    """Both tripods bumped / re-set: camera positions shifted (in) and aim point shifted."""
    from hiveshot import placement, synth
    from hiveshot.models import CameraIntrinsics
    rec = placement.recommend("usb")
    out = []
    for (name, k), d, j in ((("cam0", "A"), d0, aim_jit[0]), (("cam1", "B"), d1, aim_jit[1])):
        c = rec["cameras"][k]
        W, H = 1920, 1080
        f = fx if fx is not None else placement.hfov_to_fx(rec["hfov_deg"], W)
        pos = np.array(c["pos"], float) + np.array(d)
        la = np.array(c["look_at"], float) + np.array([j * 3.0, -j * 2.0, 0.0])
        vc = synth.VirtualCamera.look_at(name, tuple(pos), tuple(la), W, H, f)
        out.append(synth.VirtualCamera(CameraIntrinsics(name, W, H, f, f, W / 2, H / 2, (0, 0, 0, 0, 0)), vc.extr))
    return out


def core(port, real, trap, label):
    work = SCR / label
    if work.exists():
        shutil.rmtree(work)
    (work / "data").mkdir(parents=True)
    truth = S.truth_cams("usb", fx=None)
    put("mode", dict(real=real, trap=trap))
    t0 = time.time()
    aud, ids_a = scene_set_mode(work, truth, "aud", real)
    far, _ = scene_set_mode(work, truth, "far", real, hive_up="far")
    put("tags_drawn", ids_a)
    put("render_scene_s", round(time.time() - t0, 1))
    srv = S.Server(port, work / "data")
    api = srv.start()
    try:
        cfg = api.ok("GET", "/api/config")
        srcs = srcs_from(aud)
        R.apply_sources(api, cfg, [dict(s, cam_id=f"dev{i}") for i, s in enumerate(srcs)], {})
        cfg = api.ok("GET", "/api/config")
        time.sleep(0.8)
        R.apply_sources(api, cfg, srcs, {})
        wait_stable(api)
        if trap:
            c, r, dt = timed(api, "auto", "POST", "/api/calib/auto_all", {"source": "kit"})
            put("2_trap_auto_all", dict(code=c, s=dt, **(summ(r) if c == 200 else {"detail": r})))
            put("2_trap_accuracy", accuracy(api, truth))
            c, r, dt = timed(api, "finish", "POST", "/api/setup/finish")
            put("2_trap_finish", dict(code=c, s=dt, body=r))
        # lens step (wizard step 2)
        t0 = time.time()
        L = lens_step(api, truth, work, {"cam0", "cam1"}, (18, 36), "near")
        put("3_lens", {c: dict(stop=v["stop"], stop_s=v["stop_s"], out=v["out"], warnings=v["after_status"]["warnings"],
                               fx=v["after_calib"]["fx"], isrc=v["after_status"]["cams"]) for c, v in L.items()})
        put("3_lens_total_wall_s", round(time.time() - t0, 1))
        set_sources(api, srcs_from(aud))
        put("3_after_lens_status", status_brief(api))
        # kit calibration
        c, r, dt = timed(api, "auto", "POST", "/api/calib/auto_all", {"source": "kit"})
        put("4_kit_auto_all", dict(code=c, s=dt, **(summ(r) if c == 200 else {"detail": r})))
        put("4_kit_status", status_brief(api))
        put("4_kit_accuracy", accuracy(api, truth))
        c, r, dt = timed(api, "xc", "POST", "/api/calib/crosscheck")
        put("4_kit_crosscheck", dict(code=c, s=dt, max_error_in=r.get("max_error_in"), out_of_sample=r.get("out_of_sample"), held_out=r.get("held_out"),
                                      warning=r.get("warning"), detail=r.get("detail"), n_points=len(r.get("points", []))))
        c, r, dt = timed(api, "finish", "POST", "/api/setup/finish")
        put("4_finish", dict(code=c, s=dt, body=r))
        if c != 200 and not real:
            return
        # learn (wizard step 4), far first then audience then far
        L2 = {}
        for nm, vids, up in (("far_first", far, "far"), ("audience", aud, "audience"), ("far_after_audience", far, "far")):
            set_sources(api, srcs_from(vids))
            c, r, dt = timed(api, "learn", "POST", "/api/calib/hive_tags/learn", {"state": {"alliance": "red", "up_cell": up}})
            L2[nm] = dict(code=c, s=dt, body={k: r.get(k) for k in ("learned", "complete", "learned_ids", "missing_ids", "max_residual_in", "up_cell_error_in", "visible_per_camera", "reason", "detail")})
            put("5_learn", L2)
        set_sources(api, srcs_from(aud))
        c, r, dt = timed(api, "finish", "POST", "/api/setup/finish")
        put("5_finish_after_learn", dict(code=c, body=r))

        G = {}

        def restore(name):
            set_sources(api, srcs_from(aud))
            c, r, dt = timed(api, "auto", "POST", "/api/calib/auto_all", {"source": "kit"})
            G[name]["restore"] = dict(code=c, ok=r.get("ok") if c == 200 else None, acc=accuracy(api, truth))
            put("6_gates", G)

        # G1: cam1 at 720p vs 1080p intrinsics
        p720, _ = scene_set_mode(work, truth, "r720", real, size_override={"cam1": (1280, 720)})
        set_sources(api, srcs_from(p720))
        before = calib_brief(api)["raw_ext"]
        c, r, dt = timed(api, "auto", "POST", "/api/calib/auto_all", {"source": "kit"})
        after = calib_brief(api)["raw_ext"]
        G["g1_720p_cam1"] = dict(code=c, s=dt, status=status_brief(api), res=(summ(r) if c == 200 else r),
                                 cam0_changed=before["cam0"] != after["cam0"], cam1_changed=before["cam1"] != after["cam1"])
        c2, r2, _ = timed(api, "finish", "POST", "/api/setup/finish")
        G["g1_720p_cam1"]["finish"] = dict(code=c2, body={k: r2.get(k) for k in ("ok", "detail", "max_error_in", "out_of_sample")})
        put("6_gates", G)
        restore("g1_720p_cam1")

        variants = {
            "g2a_one_tag_2in_x": {101: (-2.0, 0.0)},
            "g2b_all_four_2in_mixed": {100: (2.0, 0.0), 101: (-2.0, 0.0), 102: (0.0, 2.0), 103: (2.0, -2.0)},
            "g2c_all_four_1in_low": {100: (0, -1.0), 101: (0, -1.0), 102: (0, -1.0), 103: (0, -1.0)},
            "g2d_one_base_1in_low": {102: (0, -1.0)},
        }
        for name, tape in variants.items():
            gp, _ = scene_set_mode(work, truth, name, real, tape_off=tape)
            set_sources(api, srcs_from(gp))
            good_before = calib_brief(api)["raw_ext"]
            c, r, dt = timed(api, "auto", "POST", "/api/calib/auto_all", {"source": "kit"})
            now = calib_brief(api)["raw_ext"]
            entry = dict(code=c, s=dt, res=(summ(r) if c == 200 else r),
                         cam0_changed=good_before["cam0"] != now["cam0"], cam1_changed=good_before["cam1"] != now["cam1"],
                         acc_after=accuracy(api, truth))
            c2, r2, _ = timed(api, "finish", "POST", "/api/setup/finish")
            entry["finish"] = dict(code=c2, body={k: r2.get(k) for k in ("ok", "detail", "max_error_in", "out_of_sample", "calibration_source")})
            G[name] = entry
            put("6_gates", G)
            restore(name)

        # G3: swap after a good calibration
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

        # D2: BOTH tripods moved (new venue / bumped): can the operator re-calibrate?
        set_sources(api, srcs_from(aud))
        c, r, dt = timed(api, "auto", "POST", "/api/calib/auto_all", {"source": "kit"})   # make sure baseline is good
        mt = moved_truth()
        mp, _ = scene_set_mode(work, mt, "moved", real)
        set_sources(api, srcs_from(mp))
        before = calib_brief(api)["raw_ext"]
        c, r, dt = timed(api, "auto", "POST", "/api/calib/auto_all", {"source": "kit"})
        after = calib_brief(api)["raw_ext"]
        D = dict(code=c, s=dt, res=(summ(r) if c == 200 else r), cam0_changed=before["cam0"] != after["cam0"], cam1_changed=before["cam1"] != after["cam1"])
        if c == 200:
            D["acc_vs_moved_truth"] = accuracy(api, mt)
        c, r, dt = timed(api, "finish", "POST", "/api/setup/finish")
        D["finish"] = dict(code=c, body={k: r.get(k) for k in ("ok", "detail", "max_error_in", "out_of_sample")})
        for cam in ("cam1", "cam0"):
            c, r, dt = timed(api, "single", "POST", f"/api/calib/extrinsics/{cam}/auto", {"source": "kit"})
            D[f"single_{cam}"] = dict(code=c, detail=r.get("detail"), refused=r.get("refused"), crosscheck_error_in=r.get("crosscheck_error_in"), oos=r.get("oos_error_in"))
        put("8_both_moved", D)
    finally:
        try:
            api.call("POST", "/api/pipeline/stop")
        except Exception:
            pass
        srv.stop()
    put("api_log", api.log)


if __name__ == "__main__":
    B.SC = sys.argv[1]
    port = int(sys.argv[2])
    if sys.argv[1] == "R":
        core(port, real=True, trap=True, label="R")
    else:
        core(port, real=False, trap=False, label="E")
    print("done", sys.argv[1])

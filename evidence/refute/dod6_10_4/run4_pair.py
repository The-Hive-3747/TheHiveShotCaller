"""(1) Pair-gate lock-out: both tripods moved -> Recalibrate both / auto_all, rollback on failure, 409 hint, force_single,
pair_stale, reset.   usage: run4_pair.py E|R <port> [exe|src]"""
import sys, shutil, time
from pathlib import Path
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker\evidence\refute\dod6_10_4")
import rig4 as G
from rig4 import *
model, port = sys.argv[1], int(sys.argv[2]); mode = sys.argv[3] if len(sys.argv) > 3 else "exe"
G.NAME = f"pair_{model}"
work = SCR / f"pair_{model}"
if work.exists(): shutil.rmtree(work)
(work / "data").mkdir(parents=True)
truth = S.truth_cams("usb", fx=None)
mt = moved_truth()
t0 = time.time()
aud, ids = scene(work, truth, "aud", model)
mov, ids_m = scene(work, mt, "mov", model)
bad_mov, _ = scene(work, mt, "badmov", model, tape_off={100: (2.0, 0.0), 101: (-2.0, 0.0), 102: (0.0, 2.0), 103: (2.0, -2.0)})
put("tags_drawn_aud", ids); put("tags_drawn_moved", ids_m); put("render_s", round(time.time() - t0, 1))
boards = {c: str(SCR / "boards" / f"board_near_{c}.mp4") for c in ("cam0", "cam1")}
srv = Server4(port, work / "data", mode=mode, cwd=work / "cwd")
api = srv.start(); put("mode", mode); put("startup_s", srv.startup_s)
try:
    first_apply(api, srcs(aud))
    L = lens(api, truth, work, aud, boards)
    put("lens", {c: dict(code=v["stop_code"], rmse=v["out"].get("reprojection_rmse_px"), src=v["out"].get("intrinsics_source"), warning=v["out"].get("warning")) for c, v in L.items()})
    c, r, dt = timed(api, "POST", "/api/calib/auto_all", {"source": "kit"})
    put("0_baseline_auto_all", dict(code=c, s=dt, **summ(r))); put("0_baseline_acc", accuracy(api, truth))
    base_ext = ext_raw(api)
    c, r, dt = timed(api, "POST", "/api/setup/finish"); put("0_baseline_finish", fin_brief(c, r))

    # ---- 1a both moved: single-camera Auto-calibrate (UI: card Auto-calibrate) -> 409 + hint?
    set_sources(api, srcs(mov))
    S1 = {}
    for cam in ("cam1", "cam0"):
        c, r, dt = timed(api, "POST", f"/api/calib/extrinsics/{cam}/auto", {"source": "kit"})
        S1[cam] = dict(code=c, s=dt, detail=r.get("detail"), hint=r.get("hint"), pair_check_failed=r.get("pair_check_failed"), refused=r.get("refused"),
                       crosscheck_error_in=r.get("crosscheck_error_in"), oos=r.get("oos_error_in"), keys=sorted(r.keys()))
    S1["ext_unchanged"] = (ext_raw(api) == base_ext)
    put("1a_single_after_both_moved", S1)

    # ---- 1b force_single cam1 -> saved, cam0 pair_stale; finish 409
    c, r, dt = timed(api, "POST", "/api/calib/extrinsics/cam1/auto", {"source": "kit", "force_single": True})
    F = dict(code=c, ok=r.get("ok"), warnings=r.get("warnings"), detail=r.get("detail"), pair_stale=r.get("pair_stale"), keys=sorted(r.keys()))
    st = status_brief(api); F["status_after"] = st
    c2, r2, _ = timed(api, "POST", "/api/setup/finish"); F["finish"] = fin_brief(c2, r2)
    # a second forced solve (cam0) -> who is pair_stale
    c, r, dt = timed(api, "POST", "/api/calib/extrinsics/cam0/auto", {"source": "kit", "force_single": True})
    F["force_cam0"] = dict(code=c, ok=r.get("ok"), warnings=r.get("warnings"), detail=r.get("detail"))
    F["status_after_both_forced"] = status_brief(api)
    c2, r2, _ = timed(api, "POST", "/api/setup/finish"); F["finish_after_both_forced"] = fin_brief(c2, r2)
    F["acc_vs_moved_truth"] = accuracy(api, mt)
    put("1b_force_single", F)

    # ---- 1c restore baseline (good scene), then both moved -> auto_all
    set_sources(api, srcs(aud))
    c, r, dt = timed(api, "POST", "/api/calib/auto_all", {"source": "kit"}); put("1c_restore", dict(code=c, ok=r.get("ok"), rolled_back=r.get("rolled_back")))
    base_ext = ext_raw(api)
    set_sources(api, srcs(mov))
    c, r, dt = timed(api, "POST", "/api/calib/auto_all", {"source": "kit"})
    A = dict(code=c, s=dt, **summ(r)); A["acc_vs_moved_truth"] = accuracy(api, mt); A["changed"] = (ext_raw(api) != base_ext)
    c2, r2, _ = timed(api, "POST", "/api/setup/finish"); A["finish"] = fin_brief(c2, r2)
    A["status"] = status_brief(api)
    put("1c_auto_all_after_both_moved", A)

    # ---- 1d auto_all with garbage tags (2 in off) -> rollback keeps the good moved calibration
    good_ext = ext_raw(api)
    set_sources(api, srcs(bad_mov))
    c, r, dt = timed(api, "POST", "/api/calib/auto_all", {"source": "kit"})
    Rb = dict(code=c, s=dt, **summ(r)); Rb["unchanged"] = (ext_raw(api) == good_ext); Rb["acc_vs_moved_truth"] = accuracy(api, mt)
    Rb["status"] = status_brief(api)
    put("1d_auto_all_bad_tags_rollback", Rb)

    # ---- 1e reset {cam_id: all}: poses gone, lens kept; first-calibration failure leaves nothing saved
    c, r, dt = timed(api, "POST", "/api/calib/reset", {"cam_id": "all"})
    Z = dict(code=c, body={k: (v if k != "rollback" else "<%d ext>" % len(v.get("extrinsics", []))) for k, v in r.items()})
    Z["calib_after"] = calib_brief(api); Z["status_after"] = status_brief(api)
    c, r, dt = timed(api, "POST", "/api/calib/auto_all", {"source": "kit"})   # still looking at bad_mov
    Z["bad_first_cal"] = dict(code=c, **summ(r)); Z["after_bad_first_cal"] = calib_brief(api)
    set_sources(api, srcs(mov))
    c, r, dt = timed(api, "POST", "/api/calib/auto_all", {"source": "kit"})
    Z["good_after_reset"] = dict(code=c, ok=r.get("ok"), rolled_back=r.get("rolled_back"), max_error_in=r.get("max_error_in")); Z["acc"] = accuracy(api, mt)
    c, r, dt = timed(api, "POST", "/api/calib/reset", {"cameras": "all"}); Z["reset_cameras_all"] = dict(code=c, reset=r.get("reset"), kept=r.get("kept"))
    c, r, dt = timed(api, "POST", "/api/calib/reset", {"cam_id": "cam0"}); Z["reset_cam0_when_none"] = dict(code=c, reset=r.get("reset"), detail=r.get("detail"))
    c, r, dt = timed(api, "POST", "/api/calib/reset", {"cam_id": "nope"}); Z["reset_unknown"] = dict(code=c, detail=r.get("detail"))
    c, r, dt = timed(api, "POST", "/api/calib/reset", {}); Z["reset_empty_body"] = dict(code=c, reset=r.get("reset"))
    put("1e_reset", Z)
finally:
    try: api.call("POST", "/api/pipeline/stop")
    except Exception: pass
    srv.stop()
put("api_log", api.log)
print("done pair", model)

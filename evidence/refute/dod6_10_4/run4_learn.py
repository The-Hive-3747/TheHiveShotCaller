"""(4) Learn with one reading camera; (5) calibration state independent of the pipeline HIVE state.
usage: run4_learn.py E|R <port> [exe|src]"""
import sys, shutil, time
from pathlib import Path
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker\evidence\refute\dod6_10_4")
import rig4 as G
from rig4 import *
model, port = sys.argv[1], int(sys.argv[2]); mode = sys.argv[3] if len(sys.argv) > 3 else "exe"
G.NAME = f"learn_{model}"
work = SCR / f"learn_{model}"
if work.exists():
    shutil.rmtree(work)
(work / "data").mkdir(parents=True)
truth = S.truth_cams("usb", fx=None)
aud, ids = scene(work, truth, "aud", model)
put("tags_drawn", ids)
far, idf = scene(work, truth, "far", model, states={"red": "far", "blue": "audience"})
put("tags_drawn_far_red", idf)
mstart, idm = scene(work, truth, "mstart", model, states={"red": "audience", "blue": "far"})
put("tags_drawn_match_start", idm)
boards = {c: str(SCR / "boards" / f"board_near_{c}.mp4") for c in ("cam0", "cam1")}
srv = Server4(port, work / "data", mode=mode, cwd=work / "cwd")
api = srv.start()
KEYS = ("learned", "complete", "single_camera", "camera", "learned_ids", "missing_ids", "reason", "detail", "up_cell_error_in",
        "max_residual_in", "visible_per_camera", "pnp_error_in", "errors")


def lrn(body=None):
    c, r, dt = timed(api, "POST", "/api/calib/hive_tags/learn", body)
    return dict(code=c, s=dt, **{k: r.get(k) for k in KEYS if k in r})


def xc():
    c, r, dt = timed(api, "POST", "/api/calib/crosscheck")
    return dict(code=c, max_error_in=r.get("max_error_in"), out_of_sample=r.get("out_of_sample"), held_out=r.get("held_out"),
                warning=r.get("warning"), detail=r.get("detail"),
                names=sorted({p["name"].split(" corner")[0] for p in r.get("points", [])}))


try:
    first_apply(api, srcs(aud))
    lens(api, truth, work, aud, boards)
    c, r, dt = timed(api, "POST", "/api/calib/auto_all", {"source": "kit"})
    put("0_auto_all", dict(code=c, s=dt, **summ(r)))
    # ---- (4) learn
    L = {}
    set_sources(api, srcs(far))
    L["far_first_red_far_scene"] = lrn({"state": {"alliance": "red", "up_cell": "far"}})
    set_sources(api, srcs(aud))
    L["audience_with_state_red"] = lrn({"state": {"alliance": "red", "up_cell": "audience"}})
    L["audience_with_state_blue"] = lrn({"state": {"alliance": "blue", "up_cell": "audience"}})
    L["no_state"] = lrn(None)
    set_sources(api, srcs(far))
    L["far_after_audience"] = lrn({"state": {"alliance": "red", "up_cell": "far"}})
    put("4_learn", L)
    st = api.ok("GET", "/api/pipeline/status")
    put("4_hive_state_source", st.get("hive_state_source"))
    # ---- (5) calibration state vs pipeline state
    set_sources(api, srcs(aud))
    C = {}
    for nm, body in (("pipeline_red_audience", {"alliance": "red", "up_cell": "audience"}),
                     ("pipeline_blue_far", {"alliance": "blue", "up_cell": "far"}),
                     ("pipeline_red_far", {"alliance": "red", "up_cell": "far"})):
        c, r, dt = timed(api, "POST", "/api/hive/state", body)
        e = dict(set=c)
        e["crosscheck"] = xc()
        c, r, dt = timed(api, "POST", "/api/calib/auto_all", {"source": "kit"})
        e["auto_all_kit"] = dict(code=c, ok=r.get("ok"), max_error_in=r.get("max_error_in"),
                                 oos={k: v.get("oos_error_in") for k, v in (r.get("results") or {}).items()})
        c, r, dt = timed(api, "POST", "/api/calib/auto_all", {"source": "hive"})
        e["auto_all_hive"] = dict(code=c, ok=r.get("ok"), rolled_back=r.get("rolled_back"), max_error_in=r.get("max_error_in"),
                                  per={k: {kk: v.get(kk) for kk in ("ok", "error", "tags_used", "oos_error_in", "rmse_in")} for k, v in (r.get("results") or {}).items()})
        c, r, dt = timed(api, "POST", "/api/calib/auto_all", {"source": "kit"})   # back to kit
        c, r, dt = timed(api, "POST", "/api/setup/finish")
        e["finish"] = fin_brief(c, r)
        C[nm] = e
        put("5_calstate_independent", C)
    # scene = real match start (blue audience CELL down): what do the cameras / the gates make of it
    set_sources(api, srcs(mstart))
    put("5_scene_match_start_crosscheck", xc())
    c, r, dt = timed(api, "POST", "/api/setup/finish")
    put("5_scene_match_start_finish", fin_brief(c, r))
    c, r, dt = timed(api, "POST", "/api/calib/auto_all", {"source": "kit"})
    put("5_scene_match_start_auto_all", dict(code=c, **summ(r)))
finally:
    try:
        api.call("POST", "/api/pipeline/stop")
    except Exception:
        pass
    srv.stop()
put("api_log", api.log)
print("done learn", model)

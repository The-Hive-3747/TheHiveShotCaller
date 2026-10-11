"""(3) In-sample finish. usage: run4_insample.py E|R <port> [exe|src]"""
import sys, shutil, time
from pathlib import Path
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker\evidence\refute\dod6_10_4")
import rig4 as G
from rig4 import *
model, port = sys.argv[1], int(sys.argv[2]); mode = sys.argv[3] if len(sys.argv) > 3 else "exe"
G.NAME = f"insample_{model}"
work = SCR / f"insample_{model}"
if work.exists():
    shutil.rmtree(work)
(work / "data").mkdir(parents=True)
truth = S.truth_cams("usb", fx=None)
aud, ids = scene(work, truth, "aud", model)
put("tags_drawn", ids)
V = {
    "g1_all4_1in_low": dict(tape_off={100: (0, -1.0), 101: (0, -1.0), 102: (0, -1.0), 103: (0, -1.0)}),
    "g2_base102_1in_low": dict(tape_off={102: (0, -1.0)}),
    "g3_one_tag101_1in_x": dict(tape_off={101: (-1.0, 0.0)}),
    "g4_cam1_720p": dict(size_override={"cam1": (1280, 720)}),
}
sc = {k: scene(work, truth, k, model, **v)[0] for k, v in V.items()}
boards = {c: str(SCR / "boards" / f"board_near_{c}.mp4") for c in ("cam0", "cam1")}
srv = Server4(port, work / "data", mode=mode, cwd=work / "cwd")
api = srv.start()


def ui_needs_ack(r):
    ws = list(r.get("warnings") or []) + ([r["warning"]] if r.get("warning") else [])
    return (r.get("out_of_sample") is False) or any("in-sample" in str(w).lower() for w in ws)


try:
    first_apply(api, srcs(aud))
    lens(api, truth, work, aud, boards)
    c, r, dt = timed(api, "POST", "/api/calib/auto_all", {"source": "kit"})
    put("0_baseline_auto_all", dict(code=c, s=dt, **summ(r)))
    put("0_baseline_acc", accuracy(api, truth))
    c, r, dt = timed(api, "POST", "/api/setup/finish")
    put("0_baseline_finish", dict(fin_brief(c, r), ui_needs_ack=ui_needs_ack(r)))
    c, r, dt = timed(api, "POST", "/api/calib/crosscheck")
    put("0_baseline_crosscheck", dict(code=c, max_error_in=r.get("max_error_in"), out_of_sample=r.get("out_of_sample"), held_out=r.get("held_out"), warning=r.get("warning")))
    G_ = {}
    for name, paths in sc.items():
        base_ext = ext_raw(api)
        set_sources(api, srcs(paths))
        c, r, dt = timed(api, "POST", "/api/calib/auto_all", {"source": "kit"})
        e = dict(code=c, s=dt, res=summ(r), changed=(ext_raw(api) != base_ext), acc=accuracy(api, truth), status=status_brief(api))
        c2, r2, _ = timed(api, "POST", "/api/setup/finish")
        e["finish"] = dict(fin_brief(c2, r2), ui_needs_ack=(ui_needs_ack(r2) if c2 == 200 else None))
        c3, r3, _ = timed(api, "POST", "/api/calib/crosscheck")
        e["crosscheck"] = dict(code=c3, max_error_in=r3.get("max_error_in"), out_of_sample=r3.get("out_of_sample"), warning=r3.get("warning"), detail=r3.get("detail"))
        G_[name] = e
        put("gates", G_)
        set_sources(api, srcs(aud))
        c, r, dt = timed(api, "POST", "/api/calib/auto_all", {"source": "kit"})
        G_[name]["restore"] = dict(code=c, ok=r.get("ok"), acc=accuracy(api, truth))
        put("gates", G_)
    # swapped pair after a good calibration
    swp = {"cam0": aud["cam1"], "cam1": aud["cam0"]}
    set_sources(api, srcs(swp))
    W = dict(status=status_brief(api))
    c, r, dt = timed(api, "POST", "/api/calib/crosscheck")
    W["crosscheck"] = dict(code=c, max_error_in=r.get("max_error_in"), out_of_sample=r.get("out_of_sample"), warning=r.get("warning"), detail=r.get("detail"))
    c, r, dt = timed(api, "POST", "/api/setup/finish")
    W["finish"] = dict(fin_brief(c, r), ui_needs_ack=(ui_needs_ack(r) if c == 200 else None))
    c, r, dt = timed(api, "POST", "/api/calib/auto_all", {"source": "kit"})
    W["auto_all_swapped"] = dict(code=c, res=summ(r))
    c, r, dt = timed(api, "POST", "/api/setup/finish")
    W["finish_after_resolve"] = dict(fin_brief(c, r), ui_needs_ack=(ui_needs_ack(r) if c == 200 else None))
    put("swap", W)
finally:
    try:
        api.call("POST", "/api/pipeline/stop")
    except Exception:
        pass
    srv.stop()
put("api_log", api.log)
print("done insample", model)

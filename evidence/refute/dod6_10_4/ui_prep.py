"""Leave a PATCHED SOURCE server (never probes capture devices) running on <port>, calibrated in model R (only camera B reads
the HIVE stickers), for a real-UI check in the browser pane.  usage: ui_prep.py <port> <stage> ; stage: fresh|cal|moved
Writes the server pid to ui_prep.pid and then sleeps until killed (kill that pid only)."""
import sys, os, time, shutil, json
from pathlib import Path
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker\evidence\refute\dod6_10_4")
import rig4 as G
from rig4 import *
port, stage = int(sys.argv[1]), sys.argv[2]
model = sys.argv[3] if len(sys.argv) > 3 else "R"
G.NAME = f"ui_prep_{stage}"
work = SCR / f"ui_{stage}"
if work.exists():
    shutil.rmtree(work)
(work / "data").mkdir(parents=True)
truth = S.truth_cams("usb", fx=None)
src_work = SCR / f"insample_{model}"
aud = {c: str(src_work / "vid" / f"aud_{c}.mp4") for c in ("cam0", "cam1")}
boards = {c: str(SCR / "boards" / f"board_near_{c}.mp4") for c in ("cam0", "cam1")}
srv = Server4(port, work / "data", mode="src", cwd=work / "cwd")
api = srv.start()
(HERE / "ui_prep.pid").write_text(str(srv.p.pid))
if stage == "fresh":
    cfg = api.ok("GET", "/api/config")
    m = json.loads(json.dumps(cfg))
    m["sources"] = [dict(cam_id=f"cam{i}", kind="device", target=str(t), width=1920, height=1080, fps_hint=60, backend="auto", loop=False, realtime=True)
                    for i, t in enumerate((8, 9))]
    print(api.call("PUT", "/api/config", m)[0])
else:
    first_apply(api, srcs(aud))
    lens(api, truth, work, aud, boards)
    if stage == "cal":
        c, r, dt = timed(api, "POST", "/api/calib/auto_all", {"source": "kit"})
        print("auto_all", c, r.get("ok"))
print("ready", port, srv.p.pid, flush=True)
while True:
    time.sleep(5)

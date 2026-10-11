"""(6) packaged exe: temp cwd, temp data dir, browser default (BROWSER env logger), fresh state."""
import json, sys, time, os
from pathlib import Path
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker\evidence\refute\dod6_10_4")
import rig4 as G
work = G.SCR / "t6"
import shutil
if work.exists(): shutil.rmtree(work)
(work / "cwd").mkdir(parents=True); (work / "data").mkdir(parents=True)
calls = work / "browser_calls.txt"
cmd = work / "fakebrowser.cmd"
cmd.write_text(f'@echo BROWSER_OPEN %1>> "{calls}"\r\n', encoding="ascii")
out = {}
# A: default launch (no flags except port/data-dir): does the exe try to open a browser?
class S2(G.Server4):
    def start(self, timeout=90):
        Path(self.datadir).mkdir(parents=True, exist_ok=True)
        import subprocess
        self.logf = open(work / "exe_A.log", "w")
        env = dict(os.environ); env["BROWSER"] = str(cmd)
        self.p = subprocess.Popen([str(G.EXE), "--port", str(self.port), "--data-dir", self.datadir], cwd=str(work / "cwd"),
                                  stdout=self.logf, stderr=subprocess.STDOUT, env=env)
        api = G.S.Api(self.port); t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                api.call("GET", "/api/config", timeout=2); self.startup_s = round(time.time() - t0, 1); return api
            except Exception: time.sleep(0.4)
        raise RuntimeError("no start")
srv = S2(8798, work / "data")
api = srv.start()
out["startup_s"] = srv.startup_s
time.sleep(3.5)
out["browser_calls_default_launch"] = calls.read_text() if calls.exists() else None
cfg = api.ok("GET", "/api/config")
out["default_sources"] = [(s["cam_id"], s["kind"], s["target"]) for s in cfg["sources"]]
def snap(label):
    st = api.ok("GET", "/api/pipeline/status"); c = api.ok("GET", "/api/calib")
    out[label] = dict(running=st["running"], calibration_loaded=st["calibration_loaded"], calibration_source=st["calibration_source"],
        intrinsics_default=st["intrinsics_default"], warnings=st["warnings"],
        cams={k: (v.get("calibration_source"), v.get("intrinsics_source")) for k, v in st["cameras"].items()},
        calib_intr=len(c.get("intrinsics", [])), calib_extr=len(c.get("extrinsics", [])))
snap("default_config")
api.ok("GET", "/api/calib/tags.pdf"); 
m = json.loads(json.dumps(cfg))
m["sources"] = [dict(cam_id=f"cam{i}", kind="device", target=str(t), width=1920, height=1080, fps_hint=60, backend="auto", loop=False, realtime=True) for i, t in enumerate((8, 9))]
c, new, _ = api.call("PUT", "/api/config", m)
out["put_device"] = c
snap("device_sources_8_9")
out["wizard_opens_rule"] = ("len(sources)>=2 -> sources_configured true; calibration_loaded false -> showTab('setup')",
                            out["device_sources_8_9"]["calibration_loaded"] is False)
srv.stop()
time.sleep(1)
(work / "x").mkdir(exist_ok=True)
out["exe_log_head"] = (work / "exe_A.log").read_text(errors="replace").splitlines()[:25]
# B: --no-browser flag with the same BROWSER logger
calls.unlink(missing_ok=True)
class S3(S2):
    def start(self, timeout=90):
        import subprocess
        Path(self.datadir).mkdir(parents=True, exist_ok=True)
        self.logf = open(work / "exe_B.log", "w")
        env = dict(os.environ); env["BROWSER"] = str(cmd)
        self.p = subprocess.Popen([str(G.EXE), "--port", str(self.port), "--data-dir", self.datadir, "--no-browser"], cwd=str(work / "cwd"),
                                  stdout=self.logf, stderr=subprocess.STDOUT, env=env)
        api = G.S.Api(self.port); t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                api.call("GET", "/api/config", timeout=2); return api
            except Exception: time.sleep(0.4)
srv = S3(8798, work / "data"); api = srv.start(); time.sleep(3.5)
out["browser_calls_no_browser_flag"] = calls.read_text() if calls.exists() else None
srv.stop()
(G.HERE / "t6_exe.json").write_text(json.dumps(out, indent=1, default=str))
print(json.dumps(out, indent=1, default=str))

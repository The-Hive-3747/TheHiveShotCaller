"""Round-4 rig (re-uses dod6_10_2 simlib / run_s and dod6_10_3 sim3).  Server = the PACKAGED exe by default.

Differences from round 3:
 * server is dist/HiveShotTracker/HiveShotTracker.exe (mode "exe") run from a temp cwd with a temp --data-dir
   (mode "src" = patched source server that never probes capture devices, for /api/setup/status);
 * scenes are rendered in the REAL calibration state (both audience CELLs up: {"red":"audience","blue":"audience"});
 * model "E": both cameras decode HIVE stickers, model "R": only camera B (cam1) does (docs-faithful).
"""
import json, os, shutil, subprocess, sys, time
from pathlib import Path
import numpy as np

REPO = Path(r"C:\Users\3747h\Documents\HiveShotTracker")
HERE = Path(__file__).parent
SCR = Path(r"C:\Users\3747h\AppData\Local\Temp\claude\C--Users-3747h-Documents-HiveShotTracker\386da1de-9207-4304-8c4f-9284e5732d29\scratchpad\d4")
SCR.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(REPO / "evidence" / "refute" / "dod6_10_2"))
sys.path.insert(0, str(REPO / "evidence" / "refute" / "dod6_10_3"))
import simlib as S                      # noqa: E402
import run_s as R                       # noqa: E402
import sim3                             # noqa: E402
from hiveshot import synth, placement   # noqa: E402
from hiveshot.models import CameraIntrinsics  # noqa: E402

EXE = REPO / "dist" / "HiveShotTracker" / "HiveShotTracker.exe"
PY = str(REPO / ".venv" / "Scripts" / "python.exe")
CAL_STATE = {"red": "audience", "blue": "audience"}
_CUR = {"states": dict(CAL_STATE)}
_orig_draw = synth._draw_hive_tags


def _patched_draw(img, cam, up_cells, px=80):
    return _orig_draw(img, cam, _CUR["states"], px)


synth._draw_hive_tags = _patched_draw

OUT = {}
NAME = "x"


def put(k, v):
    OUT[k] = v
    (HERE / f"results_{NAME}.json").write_text(json.dumps(OUT, indent=1, default=str), encoding="utf-8")


class Server4:
    def __init__(self, port, datadir, mode="exe", cwd=None, extra=None, env=None):
        self.port, self.datadir, self.mode = port, str(datadir), mode
        self.cwd = str(cwd or datadir)
        self.extra, self.env, self.p = (extra or []), env, None

    def start(self, timeout=90):
        Path(self.datadir).mkdir(parents=True, exist_ok=True)
        Path(self.cwd).mkdir(parents=True, exist_ok=True)
        self.logf = open(Path(self.datadir).parent / f"server_{self.port}_{int(time.time())}.log", "w")
        env = dict(os.environ)
        if self.env:
            env.update(self.env)
        if self.mode == "exe":
            cmd = [str(EXE), "--port", str(self.port), "--data-dir", self.datadir, "--no-browser"] + self.extra
            cwd = self.cwd
        else:
            code = ("import sys; sys.path.insert(0, r'%s');"
                    "from hiveshot import ingest;"
                    "ingest.list_devices=lambda *a, **k: [];"
                    "ingest._probe_one=lambda i, out: None;"
                    "from hiveshot.app import main;"
                    "main(%r)") % (str(REPO), ["--port", str(self.port), "--data-dir", self.datadir, "--no-browser"] + self.extra)
            cmd = [PY, "-c", code]
            cwd = self.cwd
        self.p = subprocess.Popen(cmd, cwd=cwd, stdout=self.logf, stderr=subprocess.STDOUT, env=env)
        api = S.Api(self.port)
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                api.call("GET", "/api/config", timeout=2)
                self.startup_s = round(time.time() - t0, 1)
                return api
            except Exception:
                time.sleep(0.4)
        raise RuntimeError("server did not start")

    def stop(self):
        if self.p and self.p.poll() is None:
            self.p.terminate()
            try:
                self.p.wait(15)
            except subprocess.TimeoutExpired:
                self.p.kill()
        try:
            self.logf.close()
        except Exception:
            pass


# ---------------------------------------------------------------- scenes
def scene(work, truth, tag, model, states=None, kit=(100, 101, 102, 103), tape_off=None, size_override=None, tilt_off=None):
    """model E: both cams render HIVE stickers; R: only cam1 (camera B) does."""
    _CUR["states"] = dict(states or CAL_STATE)
    ball = np.array([[5.0, 30.0, 30.0]])
    p0, i0 = S.make_scene_videos(work / "vid", [truth[0]], kit, tape_off, "audience", tag, hive_tags=(model == "E"),
                                 ball_xyz=ball, size_override=size_override, tilt_off=tilt_off)
    p1, i1 = S.make_scene_videos(work / "vid", [truth[1]], kit, tape_off, "audience", tag, hive_tags=True,
                                 ball_xyz=ball, size_override=size_override, tilt_off=tilt_off)
    _CUR["states"] = dict(CAL_STATE)
    return {**p0, **p1}, {**i0, **i1}


def moved_truth(d0=(5.0, -3.0, 2.0), d1=(-4.0, 4.0, -2.0), aim_jit=(2.0, -2.0), fx=None, dist=(0, 0, 0, 0, 0)):
    rec = placement.recommend("usb")
    out = []
    for (name, k), d, j in ((("cam0", "A"), d0, aim_jit[0]), (("cam1", "B"), d1, aim_jit[1])):
        c = rec["cameras"][k]
        W, H = 1920, 1080
        f = fx if fx is not None else placement.hfov_to_fx(rec["hfov_deg"], W)
        pos = np.array(c["pos"], float) + np.array(d)
        la = np.array(c["look_at"], float) + np.array([j * 3.0, -j * 2.0, 0.0])
        vc = synth.VirtualCamera.look_at(name, tuple(pos), tuple(la), W, H, f)
        out.append(synth.VirtualCamera(CameraIntrinsics(name, W, H, f, f, W / 2, H / 2, tuple(dist)), vc.extr))
    return out


# ---------------------------------------------------------------- api helpers
def srcs(paths, size=(1920, 1080)):
    return R.load_cfg_sources(paths, size=size)


def set_sources(api, s, wait=True):
    cfg = api.ok("GET", "/api/config")
    R.apply_sources(api, cfg, s, {})
    if wait:
        R.wait_frames(api)
        time.sleep(1.5)


def first_apply(api, s):
    """Wizard step 1 does applySources twice (stop, PUT, start)."""
    cfg = api.ok("GET", "/api/config")
    R.apply_sources(api, cfg, [dict(x, cam_id=f"dev{i}") for i, x in enumerate(s)], {})
    cfg = api.ok("GET", "/api/config")
    time.sleep(0.8)
    R.apply_sources(api, cfg, s, {})
    R.wait_frames(api)
    time.sleep(1.5)


def timed(api, method, path, body=None, timeout=300):
    c, o, dt = api.call(method, path, body, timeout=timeout)
    return c, o, round(dt, 2)


def status_brief(api):
    st = api.ok("GET", "/api/pipeline/status")
    return dict(running=st["running"], calibration_loaded=st["calibration_loaded"], calibration_source=st.get("calibration_source"),
                intrinsics_default=st.get("intrinsics_default"), warnings=st["warnings"], mismatch=st.get("calibration_mismatch"),
                cams={k: dict(cs=v.get("calibration_source"), isrc=v.get("intrinsics_source"), pair_stale=v.get("pair_stale"),
                              frames=v.get("frames_read")) for k, v in st["cameras"].items()})


def ext_raw(api):
    c = api.ok("GET", "/api/calib")
    return {e["cam_id"]: (tuple(e["rvec"]), tuple(e["tvec"])) for e in c["extrinsics"]}


def calib_brief(api):
    c = api.ok("GET", "/api/calib")
    return dict(keys=list(c.keys()), n_ext=len(c["extrinsics"]), n_intr=len(c["intrinsics"]),
                fx={i["cam_id"]: round(i["fx"], 1) for i in c["intrinsics"]},
                rmse={i["cam_id"]: i.get("reprojection_rmse_px") for i in c["intrinsics"]},
                isrc={i["cam_id"]: i.get("intrinsics_source") for i in c["intrinsics"]},
                top_isrc=c.get("intrinsics_source"),
                stale={e["cam_id"]: e.get("stale") for e in c["extrinsics"]})


def summ(r):
    if not isinstance(r, dict):
        return r
    out = dict(ok=r.get("ok"), rolled_back=r.get("rolled_back"), max_error_in=r.get("max_error_in"),
               calibration_source=r.get("calibration_source"), warnings=r.get("warnings"), detail=r.get("detail"), per_cam={})
    for c, v in (r.get("results") or {}).items():
        out["per_cam"][c] = {k: v.get(k) for k in ("ok", "status", "refused", "error", "fit_residual_in", "rmse_in", "oos_error_in",
                                                    "crosscheck_error_in", "tags_used", "reprojection_px", "pair_check_failed", "hint", "warnings")}
    cc = r.get("crosscheck")
    if cc:
        out["crosscheck"] = {k: cc.get(k) for k in ("max_error_in", "out_of_sample", "held_out", "warning", "error", "detail")}
    return out


def fin_brief(c, r):
    return dict(code=c, **{k: r.get(k) for k in ("ok", "detail", "reasons", "max_error_in", "out_of_sample", "oos_error_in_per_camera",
                                                  "calibration_source", "warnings", "warning", "pair_stale_cameras",
                                                  "intrinsics_poor_cameras", "intrinsics_default_cameras") if k in r})


def accuracy(api, truth):
    a = S.accuracy(api, truth)
    if "error" in a:
        return a
    return dict(pos_err_in={c: round(v["pos_err_in"], 2) for c, v in a["cams"].items()},
                rot_err_deg={c: round(v["rot_err_deg"], 2) for c, v in a["cams"].items()},
                fx={c: (round(v["fx_app"], 1), round(v["fx_true"], 1)) for c, v in a["cams"].items()},
                traj_mean=round(a["trajectory"]["mean_in"], 2), traj_p95=round(a["trajectory"]["p95_in"], 2),
                traj_max=round(a["trajectory"]["max_in"], 2), cell_center_err=round(a["cell_opening_center_err_in"], 2))


def lens(api, truth, work, vids, boards, cams=("cam0", "cam1"), sleep=21):
    """Operator: wizard step 2, 'Start recording' / wave the board / 'Stop recording' per camera."""
    res = {}
    api.call("POST", "/api/pipeline/stop")
    for cam in truth:
        if cam.cam_id not in cams:
            continue
        s2 = srcs(vids)
        for s in s2:
            if s["cam_id"] == cam.cam_id:
                s["target"] = boards[cam.cam_id]
        set_sources(api, s2)
        c1, o1, d1 = timed(api, "POST", f"/api/calib/intrinsics/{cam.cam_id}/start")
        time.sleep(sleep)
        c2, o2, d2 = timed(api, "POST", f"/api/calib/intrinsics/{cam.cam_id}/stop", timeout=180)
        res[cam.cam_id] = dict(start=c1, stop_code=c2, stop_s=d2, out=o2)
    set_sources(api, srcs(vids))
    return res

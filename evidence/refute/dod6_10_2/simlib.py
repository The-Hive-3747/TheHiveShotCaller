"""Synthetic operator rig for the DoD 6/10 refutation (round 2).

Builds "cameras" (truth intrinsics + extrinsics from placement.recommend), renders frames
containing the printed kit tags (ids 100-103 at the HIVE frame top corners, with a white
quiet zone), the HIVE's own CELL tags, a wireframe and (optionally) a checkerboard, writes
mp4s, and offers an HTTP helper plus accuracy evaluation against the truth cameras.

Nothing here reads the app's solver results to decide anything: truth stays in this file.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import cv2
import numpy as np

import os  # noqa: E402
REPO = Path(r"C:\Users\3747h\Documents\HiveShotTracker")
ROOT = Path(os.environ.get("HS_ROOT", str(REPO)))   # HS_ROOT = frozen snapshot of hiveshot/ ui/ docs/
sys.path.insert(0, str(ROOT))
from hiveshot import calib, calib_targets, field, placement, synth, tagkit  # noqa: E402
from hiveshot.models import CameraExtrinsics, CameraIntrinsics  # noqa: E402

PY = str(REPO / ".venv" / "Scripts" / "python.exe")
DIC = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)


# ------------------------------------------------------------------ truth cameras
def truth_cams(option="usb", fx=None, dist=(0, 0, 0, 0, 0), size=(1920, 1080), swap=False):
    """VirtualCameras named cam0 (= rec camera A) and cam1 (= B), true lens `fx`/`dist`.
    swap=True returns them with the names exchanged (operator cabled them the wrong way)."""
    rec = placement.recommend(option)
    W, H = size
    out = []
    for name, k in (("cam0", "A"), ("cam1", "B")):
        c = rec["cameras"][k]
        f = fx if fx is not None else placement.hfov_to_fx(rec["hfov_deg"], W)
        vc = synth.VirtualCamera.look_at(name, c["pos"], c["look_at"], W, H, f)
        intr = CameraIntrinsics(name, W, H, f, f, W / 2, H / 2, tuple(dist))
        out.append(synth.VirtualCamera(intr, vc.extr))
    if swap:
        out = [synth.VirtualCamera(CameraIntrinsics("cam0", *[getattr(out[1].intr, a) for a in
                                                              ("width", "height", "fx", "fy", "cx", "cy", "dist")]),
                                   CameraExtrinsics("cam0", out[1].extr.rvec, out[1].extr.tvec)),
               synth.VirtualCamera(CameraIntrinsics("cam1", *[getattr(out[0].intr, a) for a in
                                                              ("width", "height", "fx", "fy", "cx", "cy", "dist")]),
                                   CameraExtrinsics("cam1", out[0].extr.rvec, out[0].extr.tvec))]
    return out


def _pinhole(cam):
    i = cam.intr
    return synth.VirtualCamera(CameraIntrinsics(i.cam_id, i.width, i.height, i.fx, i.fy, i.cx, i.cy,
                                                (0, 0, 0, 0, 0)), cam.extr)


# ------------------------------------------------------------------ rendering
def _draw_plane_tag(img, cam, tid, corners3d, margin_in=0.75, px=240, label_ok=True):
    """Warp a 36h11 tag with white quiet zone onto the 3D quad `corners3d` (TL,TR,BR,BL)."""
    c = np.asarray(corners3d, float)
    cen = c.mean(axis=0)
    r = c[1] - c[0]
    u = c[0] - c[3]
    size = np.linalg.norm(r)
    r, u = r / size, u / np.linalg.norm(u)
    s = size / 2.0
    e = s + margin_in
    ext = np.array([cen + (-e) * r + e * u, cen + e * r + e * u, cen + e * r - e * u, cen - e * r - e * u])
    if (cam.depth(ext) < 1.0).any():
        return False
    # backface: normal r x u points toward viewer? tag faces +Y (toward cameras)
    n = np.cross(r, u)
    cp = -(cam.R.T @ cam.tvec).ravel()
    if np.dot(cp - cen, n) <= 0:
        return False
    mpx = int(round(px * margin_in / size))
    tot = px + 2 * mpx
    canvas = np.full((tot, tot), 255, np.uint8)
    tag = np.zeros((px, px), np.uint8)
    cv2.aruco.generateImageMarker(DIC, tid, px, tag, 1)
    canvas[mpx:mpx + px, mpx:mpx + px] = tag
    uu, vv = cam.project(ext)
    src = np.float32([[0, 0], [tot, 0], [tot, tot], [0, tot]])
    M = cv2.getPerspectiveTransform(src, np.float32(np.c_[uu, vv]))
    size_wh = (cam.intr.width, cam.intr.height)
    warped = cv2.warpPerspective(canvas, M, size_wh, flags=cv2.INTER_AREA)
    mask = cv2.warpPerspective(np.full((tot, tot), 255, np.uint8), M, size_wh)
    img[mask > 127] = warped[mask > 127][:, None]
    return True


def tilt_quad(c, deg):
    """Rotate a tag quad (TL,TR,BR,BL) by `deg` about its bottom edge, in the plane spanned by upright u and normal n."""
    c = np.asarray(c, float)
    r = c[1] - c[0]; r /= np.linalg.norm(r)
    u = c[0] - c[3]; u /= np.linalg.norm(u)
    n = np.cross(r, u)
    pivot = 0.5 * (c[2] + c[3])
    a = math.radians(deg)
    out = []
    for p in c:
        d = p - pivot
        du, dn = d @ u, d @ n
        du2 = du * math.cos(a) - dn * math.sin(a)
        dn2 = du * math.sin(a) + dn * math.cos(a)
        out.append(pivot + (d @ r) * r + du2 * u + dn2 * n)
    return np.array(out)


def render_base(cam, kit_ids=(100, 101, 102, 103), tape_off=None, hive_up="audience",
                hive_tags=True, ball_xyz=None, bg=118, tilt_off=None):
    """Distortion-free render for `cam` (pass the pinhole version). tape_off: {id: (dx, dz)} in
    inches, the tag as taped differs from the model by this much (dx along +X, dz along +Z)."""
    W, H = cam.intr.width, cam.intr.height
    img = np.full((H, W, 3), bg, np.uint8)
    synth._draw_wireframe(img, cam, field.hive_frame_wireframe(), (150, 150, 150), 2)
    if hive_tags:
        synth._draw_hive_tags(img, cam, {"red": hive_up, "blue": "far"})
    drawn = []
    for tid in kit_ids:
        c = tagkit.tag_corners_xyz(tid).copy()
        if tape_off and tid in tape_off:
            c[:, 0] += tape_off[tid][0]
            c[:, 2] += tape_off[tid][1]
        if tilt_off and tid in tilt_off:
            c = tilt_quad(c, tilt_off[tid])
        if _draw_plane_tag(img, cam, tid, c):
            drawn.append(tid)
    if ball_xyz is not None:
        d = cam.depth(ball_xyz)[0]
        u, v = cam.project(ball_xyz)
        cv2.circle(img, (int(round(u[0])), int(round(v[0]))), max(2, int(round(cam.intr.fx * 1.4 / d))),
                   (0, 200, 255), -1, cv2.LINE_AA)
    return img, drawn


def distort(img, true_cam):
    """Apply the true lens distortion to a pinhole render."""
    i = true_cam.intr
    if not any(i.dist):
        return img
    K = true_cam.K
    D = np.array(i.dist, float)
    W, H = i.width, i.height
    uu, vv = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    pts = np.stack([uu, vv], -1).reshape(-1, 1, 2)
    und = cv2.undistortPoints(pts, K, D, P=K).reshape(H, W, 2).astype(np.float32)
    return cv2.remap(img, und[..., 0], und[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                     borderValue=(118, 118, 118))


def write_mp4(path, frame, n=60, fps=30.0, noise=2.0, seed=0):
    rng = np.random.default_rng(seed)
    h, w = frame.shape[:2]
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    base = cv2.GaussianBlur(frame, (0, 0), 0.8)
    for _ in range(n):
        f = np.clip(base.astype(np.float32) + rng.normal(0, noise, base.shape), 0, 255).astype(np.uint8)
        vw.write(f)
    vw.release()
    return str(path)


def make_scene_videos(outdir, truth, kit_ids=(100, 101, 102, 103), tape_off=None, hive_up="audience",
                      tag="scene", hive_tags=True, ball_xyz=None, size_override=None, tilt_off=None):
    """Write <outdir>/<tag>_cam0.mp4 / _cam1.mp4 and return ({cam: path}, {cam: drawn tag ids})."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    paths, ids = {}, {}
    for cam in truth:
        pin = _pinhole(cam)
        img, drawn = render_base(pin, kit_ids, tape_off, hive_up, hive_tags, ball_xyz, tilt_off=tilt_off)
        img = distort(img, cam)
        if size_override and cam.cam_id in size_override:
            img = cv2.resize(img, size_override[cam.cam_id], interpolation=cv2.INTER_AREA)
        paths[cam.cam_id] = write_mp4(outdir / f"{tag}_{cam.cam_id}.mp4", img, seed=hash(cam.cam_id) % 1000)
        ids[cam.cam_id] = drawn
        cv2.imwrite(str(outdir / f"{tag}_{cam.cam_id}.png"), img)
    return paths, ids


# ------------------------------------------------------------------ checkerboard "operator waves board"
def make_board_video(path, truth_cam, seconds=25, fps=30.0, seed=1, drop_frac=0.0, depth_range=(24, 60)):
    """A person waves the printed 10x7 / 1.00 in board in front of the camera (poses at 2..5 ft)."""
    img, _ = calib_targets.render_checkerboard()
    H0, W0 = img.shape
    DPI = 300
    bw, bh = 10, 7
    x0 = (W0 - bw * DPI) / 2
    y0 = (H0 - 0.5 * DPI - bh * DPI) / 2
    S = np.array([[1 / DPI, 0, -x0 / DPI], [0, 1 / DPI, -y0 / DPI], [0, 0, 1.0]])
    K = truth_cam.K
    D = np.array(truth_cam.intr.dist, float)
    W, H = truth_cam.intr.width, truth_cam.intr.height
    pin = np.array([[K[0, 0], 0, K[0, 2]], [0, K[1, 1], K[1, 2]], [0, 0, 1.0]])
    rng = np.random.default_rng(seed)
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))
    n = int(seconds * fps)
    npose = int(seconds / 0.5)          # pose changes every 0.5 s (one capture per 0.5 s)
    poses = []
    for _ in range(npose):
        for _try in range(200):
            rx, ry, rz = rng.uniform(-40, 40), rng.uniform(-40, 40), rng.uniform(-25, 25)
            R, _ = cv2.Rodrigues(np.radians([rx, ry, rz]).astype(np.float64))
            depth = rng.uniform(*depth_range)
            cx, cy = rng.uniform(-0.25, 0.25) * depth * W / pin[0, 0], rng.uniform(-0.2, 0.2) * depth * H / pin[0, 0]
            t = np.array([cx, cy, depth]) - R @ np.array([5.0, 3.5, 0.0])
            Hm = pin @ np.column_stack([R[:, 0], R[:, 1], t])
            c = np.array([[0, 0, 1], [10, 0, 1], [10, 7, 1], [0, 7, 1]], float).T
            pr = Hm @ c
            pr = (pr[:2] / pr[2]).T
            if (pr[:, 0] > 30).all() and (pr[:, 0] < W - 30).all() and (pr[:, 1] > 30).all() and (pr[:, 1] < H - 30).all():
                break
        poses.append(Hm @ S)
    for k in range(n):
        M = poses[min(k // int(0.5 * fps), npose - 1)]
        fr = cv2.warpPerspective(img, M, (W, H), flags=cv2.INTER_AREA, borderValue=90)
        fr = cv2.cvtColor(fr, cv2.COLOR_GRAY2BGR)
        fr = distort(fr, truth_cam)
        vw.write(fr)
    vw.release()
    return str(path)


# ------------------------------------------------------------------ HTTP helper / server
class Api:
    def __init__(self, port):
        self.base = f"http://127.0.0.1:{port}"
        self.log = []

    def call(self, method, path, body=None, timeout=120):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                ct = r.headers.get("Content-Type", "")
                code = r.status
        except urllib.error.HTTPError as e:
            raw, ct, code = e.read(), e.headers.get("Content-Type", ""), e.code
        dt = time.time() - t0
        out = json.loads(raw) if "json" in ct else {"_bytes": len(raw), "_ct": ct}
        self.log.append((method, path, code, round(dt, 2)))
        return code, out, dt

    def ok(self, *a, **k):
        code, out, dt = self.call(*a, **k)
        if code >= 400:
            raise RuntimeError(f"{a[:2]} -> {code} {out}")
        return out


class Server:
    def __init__(self, port, datadir):
        self.port, self.datadir = port, str(datadir)
        self.p = None

    def start(self):
        Path(self.datadir).mkdir(parents=True, exist_ok=True)
        self.logf = open(Path(self.datadir).parent / f"server_{self.port}.log", "w")
        self.p = subprocess.Popen([PY, "-m", "hiveshot.app", "--port", str(self.port),
                                   "--data-dir", self.datadir], cwd=str(ROOT),
                                  stdout=self.logf, stderr=subprocess.STDOUT)
        api = Api(self.port)
        t0 = time.time()
        while time.time() - t0 < 60:
            try:
                api.call("GET", "/api/config", timeout=2)
                return api
            except Exception:
                time.sleep(0.5)
        raise RuntimeError("server did not start")

    def stop(self):
        if self.p and self.p.poll() is None:
            self.p.terminate()
            try:
                self.p.wait(10)
            except subprocess.TimeoutExpired:
                self.p.kill()
        try:
            self.logf.close()
        except Exception:
            pass


# ------------------------------------------------------------------ accuracy vs truth
def _trajectory_points(n=400, seed=0):
    tr = placement.sample_trajectories()
    pts = np.vstack([np.asarray(t)[:, 1:4] if np.asarray(t).shape[1] == 4 else np.asarray(t) for t in
                     (x[1] if isinstance(x, tuple) else x for x in tr)])
    rng = np.random.default_rng(seed)
    return pts[rng.choice(len(pts), min(n, len(pts)), replace=False)]


def load_app_calib(api):
    d = api.ok("GET", "/api/calib")
    intr = {i["cam_id"]: CameraIntrinsics(**{**i, "dist": tuple(i["dist"])}) for i in d["intrinsics"]}
    ext = {}
    for e in d["extrinsics"]:
        e = dict(e)
        e.pop("stale", None)
        ext[e["cam_id"]] = CameraExtrinsics(**{**e, "rvec": tuple(e["rvec"]), "tvec": tuple(e["tvec"])})
    return intr, ext, d


def _cam_center(ext):
    R = cv2.Rodrigues(np.array(ext.rvec, float))[0]
    return -R.T @ np.array(ext.tvec, float), R


def accuracy(api_or_calib, truth, noise_px=0.3, seed=3):
    """Pose + triangulation error of the app's calibration against the truth cameras.
    `truth` is the list [cam0, cam1] of VirtualCamera that physically produced the frames.
    Mapping: app cam_id -> truth cam with the same name (a swapped rig is a *truth* property)."""
    if isinstance(api_or_calib, Api):
        intr, ext, _ = load_app_calib(api_or_calib)
    else:
        intr, ext = api_or_calib
    res = {"cams": {}}
    names = [t.cam_id for t in truth]
    if not all(n in ext for n in names):
        return {"error": "no extrinsics for " + ",".join(n for n in names if n not in ext)}
    for t in truth:
        c_app, R_app = _cam_center(ext[t.cam_id])
        c_true = -t.R.T @ t.tvec.ravel()
        dR = R_app @ t.R.T
        ang = math.degrees(math.acos(max(-1, min(1, (np.trace(dR) - 1) / 2))))
        res["cams"][t.cam_id] = {"pos_err_in": float(np.linalg.norm(c_app - c_true)), "rot_err_deg": float(ang),
                                 "fx_app": intr[t.cam_id].fx, "fx_true": t.intr.fx}
    pts = _trajectory_points()
    extra = np.array([c for _, c in [(0, np.array(p)) for _, p in calib_targets.field_reference_points()]])
    for label, P in (("trajectory", pts), ("reference_pts", extra)):
        rng = np.random.default_rng(seed)
        uv0 = np.c_[truth[0].project(P)]
        uv1 = np.c_[truth[1].project(P)]
        ok = np.ones(len(P), bool)
        for t, uv in ((truth[0], uv0), (truth[1], uv1)):
            ok &= (t.depth(P) > 1) & (uv[:, 0] > 0) & (uv[:, 0] < t.intr.width) & (uv[:, 1] > 0) & (uv[:, 1] < t.intr.height)
        uv0 = uv0[ok] + rng.normal(0, noise_px, (ok.sum(), 2))
        uv1 = uv1[ok] + rng.normal(0, noise_px, (ok.sum(), 2))
        xyz, _r = calib.triangulate(intr[names[0]], ext[names[0]], uv0, intr[names[1]], ext[names[1]], uv1)
        e = np.linalg.norm(xyz - P[ok], axis=1)
        res[label] = {"n": int(ok.sum()), "mean_in": float(e.mean()), "median_in": float(np.median(e)),
                      "p95_in": float(np.percentile(e, 95)), "max_in": float(e.max())}
    # the CELL opening centre: the single point the DoD names
    st = field.HiveState("red", "audience")
    cen, _n = field.cell_opening_plane("red", "audience", st)
    uv0 = np.c_[truth[0].project(cen)]
    uv1 = np.c_[truth[1].project(cen)]
    xyz, _r = calib.triangulate(intr[names[0]], ext[names[0]], uv0[0], intr[names[1]], ext[names[1]], uv1[0])
    res["cell_opening_center_err_in"] = float(np.linalg.norm(xyz - cen))
    return res

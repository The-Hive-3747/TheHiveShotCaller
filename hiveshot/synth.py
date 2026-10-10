"""Synthetic shots, virtual cameras and rendered video for tests/development.

CLI: python -m hiveshot.synth --out fixtures/synth_basic --shots 6 --fps 60
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from . import field
from .field_constants import FIELD_SIZE, GRAVITY_IPS2, POLLEN_DIAMETER
from .models import CameraExtrinsics, CameraIntrinsics


def simulate_trajectory(p0, v0, dt: float, t_max: float, drag_k: float = 0.0,
                        g: float = GRAVITY_IPS2) -> np.ndarray:
    """Return (N,4) [t,x,y,z]; stops before the first sample with z<0.
    drag_k=0 uses the closed-form parabola; otherwise RK4 with a=-g z - k|v|v."""
    p0 = np.asarray(p0, float)
    v0 = np.asarray(v0, float)
    n = int(math.floor(t_max / dt)) + 1
    ts = np.arange(n) * dt
    if drag_k == 0.0:
        pos = p0[None, :] + v0[None, :] * ts[:, None]
        pos[:, 2] -= 0.5 * g * ts ** 2
    else:
        gv = np.array([0.0, 0.0, -g])

        def acc(v):
            return gv - drag_k * np.linalg.norm(v) * v

        pos = np.empty((n, 3))
        p, v = p0.copy(), v0.copy()
        pos[0] = p
        for i in range(1, n):
            k1v = acc(v)
            k1p = v
            k2p = v + 0.5 * dt * k1v
            k2v = acc(k2p)
            k3p = v + 0.5 * dt * k2v
            k3v = acc(k3p)
            k4p = v + dt * k3v
            k4v = acc(k4p)
            p = p + dt / 6 * (k1p + 2 * k2p + 2 * k3p + k4p)
            v = v + dt / 6 * (k1v + 2 * k2v + 2 * k3v + k4v)
            pos[i] = p
    out = np.column_stack([ts, pos])
    bad = np.nonzero(out[:, 3] < 0)[0]
    if len(bad):
        out = out[: bad[0]]
    return out


def _z_at_range(p0, v0, rng, drag_k, hdir) -> float:
    tr = simulate_trajectory(p0, v0, 0.002, 4.0, drag_k)
    s = (tr[:, 1:3] - np.asarray(p0)[:2]) @ hdir
    idx = np.nonzero(s >= rng)[0]
    if len(idx) == 0:
        return -1e6
    i = idx[0]
    if i == 0:
        return float(tr[0, 3])
    f = (rng - s[i - 1]) / (s[i] - s[i - 1])
    return float(tr[i - 1, 3] + f * (tr[i, 3] - tr[i - 1, 3]))


def aim_for_cell(launch_point, alliance: str, which: str, state: field.HiveState,
                 speed_ips: float, drag_k: float = 0.0, arc: str = "high") -> np.ndarray:
    """Velocity vector that passes through the opening center. arc='high' picks
    the steepest elevation solution, 'low' the flattest."""
    lp = np.asarray(launch_point, float)
    center, _ = field.cell_opening_plane(alliance, which, state)
    dxy = center[:2] - lp[:2]
    rng = float(np.linalg.norm(dxy))
    hdir = dxy / rng
    zt = float(center[2])

    def vel(el):
        return np.array([hdir[0] * speed_ips * math.cos(el),
                         hdir[1] * speed_ips * math.cos(el),
                         speed_ips * math.sin(el)])

    def f(el):
        return _z_at_range(lp, vel(el), rng, drag_k, hdir) - zt

    els = np.radians(np.arange(1.0, 89.5, 1.0))
    vals = [f(e) for e in els]
    roots = []
    for i in range(len(els) - 1):
        if vals[i] > 0 >= vals[i + 1] or vals[i] <= 0 < vals[i + 1]:
            roots.append((els[i], els[i + 1], vals[i]))
    root = None if not roots else (roots[0] if arc == "low" else roots[-1])
    if root is None:
        raise ValueError("cannot reach the opening center at this speed")
    lo, hi, flo = root
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return vel(0.5 * (lo + hi))


class VirtualCamera:
    def __init__(self, intr: CameraIntrinsics, extr: CameraExtrinsics):
        self.intr = intr
        self.extr = extr
        self.K = np.array([[intr.fx, 0, intr.cx], [0, intr.fy, intr.cy], [0, 0, 1.0]])
        self.dist = np.array(intr.dist, float) if len(intr.dist) else np.zeros(5)
        self.rvec = np.array(extr.rvec, float).reshape(3, 1)
        self.tvec = np.array(extr.tvec, float).reshape(3, 1)
        self.R = cv2.Rodrigues(self.rvec)[0]

    @property
    def cam_id(self) -> str:
        return self.intr.cam_id

    def depth(self, pts) -> np.ndarray:
        pts = np.atleast_2d(np.asarray(pts, float))
        return (self.R @ pts.T + self.tvec).T[:, 2]

    def project(self, points_xyz) -> tuple[np.ndarray, np.ndarray]:
        pts = np.ascontiguousarray(np.atleast_2d(np.asarray(points_xyz, float)).reshape(-1, 3))
        uv, _ = cv2.projectPoints(pts, self.rvec, self.tvec, self.K, self.dist)
        uv = uv.reshape(-1, 2)
        return uv[:, 0], uv[:, 1]

    @staticmethod
    def look_at(cam_id: str, pos, target, width=1920, height=1080, fx=1400.0
                ) -> "VirtualCamera":
        pos = np.asarray(pos, float)
        fwd = np.asarray(target, float) - pos
        fwd /= np.linalg.norm(fwd)
        right = np.cross(fwd, [0.0, 0.0, 1.0])
        right /= np.linalg.norm(right)
        down = np.cross(fwd, right)
        R = np.vstack([right, down, fwd])
        t = -R @ pos
        rvec = cv2.Rodrigues(R)[0].ravel()
        intr = CameraIntrinsics(cam_id, width, height, fx, fx, width / 2, height / 2,
                                (0.0, 0.0, 0.0, 0.0, 0.0))
        extr = CameraExtrinsics(cam_id, tuple(float(x) for x in rvec),
                                tuple(float(x) for x in t))
        return VirtualCamera(intr, extr)


def make_default_pair(width: int = 1920, height: int = 1080, fx: float = 900.0
                      ) -> list[VirtualCamera]:
    """Two wide-angle cameras (fx=900 on 1920 px, ~94 deg HFOV), 90 deg apart,
    55 in high, 115 in from field center, both aimed at a point 45 in high
    roughly midway between the launch area and the up CELL, so whole shot arcs
    stay in frame."""
    target = np.array([-12.75, 47.0, 45.0])
    cams = []
    for name, ang in (("cam0", 45.0), ("cam1", 135.0)):
        a = math.radians(ang)
        pos = (115.0 * math.cos(a), 115.0 * math.sin(a), 55.0)
        cams.append(VirtualCamera.look_at(name, pos, target, width, height, fx))
    return cams


def in_image_fraction(truth: dict) -> float:
    """Fraction of truth ball records whose projected center is inside the image."""
    W, H = truth["intrinsics"]["width"], truth["intrinsics"]["height"]
    balls = [b for f in truth["frames"] for b in f["balls"]]
    if not balls:
        return 0.0
    ok = sum(0 <= b["u"] < W and 0 <= b["v"] < H for b in balls)
    return ok / len(balls)


def _draw_wireframe(img, cam: VirtualCamera, segs, color, thickness=2):
    h = FIELD_SIZE / 2
    floor = [(-h, -h, 0), (h, -h, 0), (h, h, 0), (-h, h, 0)]
    segs = list(segs) + [(np.array(floor[i], float), np.array(floor[(i + 1) % 4], float))
                         for i in range(4)]
    for p0, p1 in segs:
        if cam.depth(p0)[0] < 1.0 or cam.depth(p1)[0] < 1.0:
            continue
        u, v = cam.project(np.array([p0, p1]))
        cv2.line(img, (int(round(u[0])), int(round(v[0]))),
                 (int(round(u[1])), int(round(v[1]))), color, thickness, cv2.LINE_AA)


def _draw_hive_tags(img, cam: VirtualCamera, up_cells: dict, px: int = 80):
    """Warp real 36h11 tag images onto the projected HIVE tag faces (back-facing and
    behind-camera tags are skipped). Returns the ids drawn."""
    dic = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    cam_pos = -(cam.R.T @ cam.tvec).ravel()
    src = np.float32([[0, 0], [px - 1, 0], [px - 1, px - 1], [0, px - 1]])
    drawn = []
    jobs = []
    size = (cam.intr.width, cam.intr.height)
    m = px // 2  # white sticker margin around each tag
    shift = np.array([[1.0, 0, -m], [0, 1.0, -m], [0, 0, 1.0]])
    for al in field.ALLIANCES:
        st = field.HiveState(al, up_cells.get(al, "audience"))
        for which in field.CELLS:
            _, _, _, nrm = field.cell_floor_frame(al, which, st)
            for tid, cor in field.hive_tag_corners(al, which, st).items():
                if np.dot(cam_pos - cor.mean(axis=0), nrm) <= 0 or (cam.depth(cor) < 1.0).any():
                    continue
                u, v = cam.project(cor)
                M = cv2.getPerspectiveTransform(src, np.float32(np.c_[u, v]))
                jobs.append((tid, M))
    # pass 1: white sticker margins (so neighbours do not overwrite each other's border)
    for _, M in jobs:
        mask = cv2.warpPerspective(np.full((px + 2 * m, px + 2 * m), 255, np.uint8), M @ shift, size)
        img[mask > 127] = 255
    # pass 2: the tags themselves
    for tid, M in jobs:
        tag = np.zeros((px, px), np.uint8)
        cv2.aruco.generateImageMarker(dic, tid, px, tag, 1)
        warped = cv2.warpPerspective(tag, M, size, flags=cv2.INTER_AREA)
        mask = cv2.warpPerspective(np.full((px, px), 255, np.uint8), M, size)
        img[mask > 127] = warped[mask > 127][:, None]
        drawn.append(tid)
    return drawn


def _interp(traj: np.ndarray, t: float) -> Optional[np.ndarray]:
    if t < traj[0, 0] or t > traj[-1, 0]:
        return None
    return np.array([np.interp(t, traj[:, 0], traj[:, k]) for k in (1, 2, 3)])


def render_sequence(trajectories, cams, fps: float, out_dir, ball_radius_in: float = POLLEN_DIAMETER / 2,
                    ball_color_bgr=(0, 200, 255), background: str = "field",
                    tail_s: float = 0.2, with_hive_tags: bool = False,
                    hive_up_cells: Optional[dict] = None) -> dict:
    """Render each camera to <out_dir>/<cam_id>.mp4 plus <cam_id>_truth.json.
    trajectories: list of (t_offset, traj[N,4]). with_hive_tags=True also renders the
    36h11 HIVE tags (default red audience-up, blue far-up) into the frames.
    Returns cam_id -> mp4 path."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    end = max(off + tr[-1, 0] for off, tr in trajectories) + tail_s
    n_frames = int(math.ceil(end * fps)) + 1
    segs = field.hive_frame_wireframe() if background == "field" else []
    paths = {}
    for cam in cams:
        W, H = cam.intr.width, cam.intr.height
        bg = np.full((H, W, 3), 40, np.uint8)
        if background == "field":
            _draw_wireframe(bg, cam, segs, (150, 150, 150))
        if with_hive_tags:
            _draw_hive_tags(bg, cam, hive_up_cells or {"red": "audience", "blue": "far"})
        path = out / f"{cam.cam_id}.mp4"
        vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))
        if not vw.isOpened():
            raise RuntimeError("cannot open VideoWriter")
        frames = []
        for fi in range(n_frames):
            t = fi / fps
            img = bg.copy()
            balls = []
            for bi, (off, tr) in enumerate(trajectories):
                p = _interp(tr, t - off)
                if p is None:
                    continue
                d = cam.depth(p)[0]
                if d < 1.0:
                    continue
                u, v = cam.project(p)
                rpx = cam.intr.fx * ball_radius_in / d
                cv2.circle(img, (int(round(u[0])), int(round(v[0]))),
                           max(1, int(round(rpx))), ball_color_bgr, -1, cv2.LINE_AA)
                balls.append({"ball": bi, "xyz": p.tolist(), "u": float(u[0]),
                              "v": float(v[0]), "radius_px": float(rpx)})
            vw.write(img)
            frames.append({"frame_idx": fi, "t": t, "balls": balls})
        vw.release()
        truth = {
            "cam_id": cam.cam_id, "fps": fps, "n_frames": n_frames,
            "ball_radius_in": ball_radius_in,
            "t_offsets": [float(o) for o, _ in trajectories],
            "intrinsics": cam.intr.__dict__ | {"dist": list(cam.intr.dist)},
            "extrinsics": cam.extr.__dict__ | {"rvec": list(cam.extr.rvec), "tvec": list(cam.extr.tvec)},
            "frames": frames,
        }
        (out / f"{cam.cam_id}_truth.json").write_text(json.dumps(truth))
        paths[cam.cam_id] = str(path)
    return paths


def _flight_visible(tr: np.ndarray, cams) -> bool:
    for cam in cams:
        if (cam.depth(tr[:, 1:]) < 1.0).any():
            return False
        u, v = cam.project(tr[:, 1:])
        if ((u < 0) | (u >= cam.intr.width) | (v < 0) | (v >= cam.intr.height)).any():
            return False
    return True


def build_shots(offsets, seed: int = 1, max_apex: float = 84.0, cams=None):
    """One shot per t_launch in offsets. Launch points are 60-110 in (3D) from the
    up CELL center (inside the field), apex <= max_apex, whole flight inside every
    camera in `cams` (default pair). Every third shot is aimed off-azimuth so
    it misses. Flights end at the field wall or on entering the opening.
    Returns (trajectories, shot_info)."""
    cams = make_default_pair() if cams is None else cams
    rng = np.random.default_rng(seed)
    st = field.HiveState("red", "audience")
    center, _ = field.cell_opening_plane("red", "audience", st)
    radius = POLLEN_DIAMETER / 2
    h = FIELD_SIZE / 2
    trajs, info = [], []
    for i, t0 in enumerate(offsets):
        while True:
            lp = np.array([rng.uniform(-66, 66), rng.uniform(25, 68), 12.0])
            if not 60.0 <= np.linalg.norm(lp - center) <= 110.0:  # 3D distance to the cell
                continue
            speed = float(rng.uniform(220, 340))
            try:
                v0 = aim_for_cell(lp, "red", "audience", st, speed,
                                  arc="high")
            except ValueError:
                continue
            if not 66.0 <= lp[2] + v0[2] ** 2 / (2 * GRAVITY_IPS2) <= max_apex:
                continue
            if i % 3 == 2:  # deliberate miss
                a_ = math.radians(rng.choice([-1, 1]) * rng.uniform(12, 20))
                c, s_ = math.cos(a_), math.sin(a_)
                v0 = np.array([c * v0[0] - s_ * v0[1], s_ * v0[0] + c * v0[1], v0[2]])
            tr = simulate_trajectory(lp, v0, 1 / 1000, 3.0)
            end = len(tr)
            outside = np.nonzero((np.abs(tr[:, 1]) > h) | (np.abs(tr[:, 2]) > h))[0]
            if len(outside):
                end = int(outside[0])
            made = False
            for k in range(end - 1):
                if field.segment_crosses_opening(tr[k, 1:], tr[k + 1, 1:], "red",
                                                 "audience", st, radius):
                    made = True
                    end = k + 2
                    break
            tr = tr[:end]
            if _flight_visible(tr, cams):
                break
        trajs.append((float(t0), tr))
        info.append({"shot": i, "t_launch": float(t0), "launch_point": lp.tolist(),
                     "speed_ips": speed, "v0": v0.tolist(), "made": bool(made),
                     "apex_z_in": float(tr[:, 3].max()), "duration_s": float(tr[-1, 0])})
    return trajs, info


def _parse_bursts(spec: str, spacing: float, gap: float):
    offs, t = [], 0.0
    for bi, n in enumerate(int(x) for x in spec.split(",")):
        if bi:
            t += gap
        for k in range(n):
            if k:
                t += spacing
            offs.append(t)
    return offs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hiveshot.synth")
    ap.add_argument("--out", required=True)
    ap.add_argument("--shots", type=int, default=6)
    ap.add_argument("--bursts", default=None,
                    help="comma list of burst sizes, e.g. 4,2 (overrides --shots)")
    ap.add_argument("--spacing", type=float, default=0.25, help="s between shots in a burst")
    ap.add_argument("--gap", type=float, default=3.0,
                    help="s from last launch of a burst to first launch of the next")
    ap.add_argument("--fps", type=float, default=60.0)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(argv)
    offs = _parse_bursts(a.bursts or str(a.shots), a.spacing, a.gap)
    trajs, info = build_shots(offs, a.seed)
    cams = make_default_pair()
    paths = render_sequence(trajs, cams, a.fps, a.out)
    Path(a.out, "shots.json").write_text(json.dumps(info, indent=1))
    print(f"cameras: {paths}")
    for cam in cams:
        tr = json.loads(Path(a.out, f"{cam.cam_id}_truth.json").read_text())
        print(f"{cam.cam_id}: in-image fraction {in_image_fraction(tr):.3f}")
    for s in info:
        print(f"shot {s['shot']}: t_launch={s['t_launch']:.2f}s speed={s['speed_ips']:.0f} ips "
              f"apex={s['apex_z_in']:.0f} in flight={s['duration_s']:.2f}s made={s['made']}")
    print(f"made {sum(s['made'] for s in info)}/{len(info)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

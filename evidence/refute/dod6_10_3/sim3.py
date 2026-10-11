"""Round-3 rig helpers (re-uses dod6_10_2/simlib.py; live tree; ROOT = repo)."""
import sys, math, json, time
from pathlib import Path
import cv2, numpy as np
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker\evidence\refute\dod6_10_2")
import simlib as S
from hiveshot import calib_targets


def make_board_video3(path, truth_cam, seconds=25, fps=30.0, seed=1, depth_range=(18, 36), tilt=30.0, rz=20.0):
    """Operator waves the printed 10x7/1.00in board 1.5-3 ft away (depth to board centre), tilted +-tilt deg,
    pose changes every 0.5 s. Board image = hiveshot.calib_targets.render_checkerboard() (what the PDF prints)."""
    img, _ = calib_targets.render_checkerboard()
    H0, W0 = img.shape
    DPI = 300
    bw, bh = 10, 7
    x0 = (W0 - bw * DPI) / 2
    y0 = (H0 - 0.5 * DPI - bh * DPI) / 2
    Smat = np.array([[1 / DPI, 0, -x0 / DPI], [0, 1 / DPI, -y0 / DPI], [0, 0, 1.0]])
    K = truth_cam.K
    W, H = truth_cam.intr.width, truth_cam.intr.height
    pin = np.array([[K[0, 0], 0, K[0, 2]], [0, K[1, 1], K[1, 2]], [0, 0, 1.0]])
    rng = np.random.default_rng(seed)
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))
    n = int(seconds * fps)
    npose = int(seconds / 0.5)
    poses = []
    vis = 0
    for _ in range(npose):
        ok = False
        for _try in range(400):
            rx, ry, rzz = rng.uniform(-tilt, tilt), rng.uniform(-tilt, tilt), rng.uniform(-rz, rz)
            R, _ = cv2.Rodrigues(np.radians([rx, ry, rzz]).astype(np.float64))
            depth = rng.uniform(*depth_range)
            cx, cy = rng.uniform(-0.3, 0.3) * depth * W / pin[0, 0], rng.uniform(-0.25, 0.25) * depth * H / pin[0, 0]
            t = np.array([cx, cy, depth]) - R @ np.array([5.0, 3.5, 0.0])
            Hm = pin @ np.column_stack([R[:, 0], R[:, 1], t])
            c = np.array([[0, 0, 1], [10, 0, 1], [10, 7, 1], [0, 7, 1]], float).T
            pr = Hm @ c
            pr = (pr[:2] / pr[2]).T
            if (pr[:, 0] > 30).all() and (pr[:, 0] < W - 30).all() and (pr[:, 1] > 30).all() and (pr[:, 1] < H - 30).all():
                ok = True
                break
        vis += ok
        poses.append(Hm @ Smat)
    for k in range(n):
        M = poses[min(k // int(0.5 * fps), npose - 1)]
        fr = cv2.warpPerspective(img, M, (W, H), flags=cv2.INTER_AREA, borderValue=90)
        fr = cv2.cvtColor(fr, cv2.COLOR_GRAY2BGR)
        fr = S.distort(fr, truth_cam)
        fr = np.clip(fr.astype(np.float32) + rng.normal(0, 1.5, fr.shape), 0, 255).astype(np.uint8)
        vw.write(fr)
    vw.release()
    return str(path), vis, npose

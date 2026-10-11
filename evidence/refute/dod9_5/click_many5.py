"""Click method (8 CELL corners) with the operator placement error (+-1 in, +-0.5 in lens, +-2 deg, +-1 deg roll),
300 seeds per row, both options, sigma 1.0 / 1.5 px per axis. Counts solver exceptions (PnP RANSAC failed) as failures.
Gate: RMSE < 2 px and no point > 3 px. Opening center error vs CAD from the two clicked cameras (noise = sigma).
Run: PYTHONPATH=. .venv/Scripts/python.exe evidence/refute/dod9_5/click_many5.py [nseeds]"""
import sys
import numpy as np
sys.path.insert(0, "evidence/refute/dod9_2")
import sim as S
from hiveshot import calib, calib_targets as ct

N = int(sys.argv[1]) if len(sys.argv) > 1 else 300
pts8 = np.array([p for _, p in ct.field_reference_points()])
for opt in ("usb", "gopro"):
    for sigma in (0.7, 1.0, 1.5):
        cam_ok = [0, 0]; cam_exc = [0, 0]; cam_rm = [0, 0]; pair = 0; pair_exc = 0; pair_1in = 0
        oc = []
        for seed in range(N):
            rng = np.random.default_rng(51000 + seed)
            cams = [S.true_cam(opt, "A", rng, "cam0"), S.true_cam(opt, "B", rng, "cam1")]
            exts, flags = [], []
            for k, cam in enumerate(cams):
                u, v = cam.project(pts8)
                uv = np.c_[u, v] + rng.normal(0, sigma, (8, 2))
                try:
                    e = calib.solve_extrinsics_from_points(cam.intr, uv, pts8, f"cam{k}")
                    rep = calib.reprojection_report(cam.intr, e, uv, pts8)
                    per = np.array(rep["per_point_px"])
                    g = bool(rep["rmse_px"] < 2 and per.max() < 3)
                    cam_rm[k] += rep["rmse_px"] < 2
                    cam_ok[k] += g
                    flags.append(g)
                    exts.append(e)
                except ValueError:
                    cam_exc[k] += 1
                    flags.append(False)
                    exts.append(None)
            if all(e is not None for e in exts):
                oc.append(S.triang_errors(cams, exts, rng, sigma)["opening_center"])
            else:
                pair_exc += 1
            pair += all(flags)
            pair_1in += all(flags) and oc and (len(oc) and oc[-1] < 1)
        print(f"{opt:6s} sigma {sigma}: per-camera gate cam0 {cam_ok[0]/N:.2f} cam1 {cam_ok[1]/N:.2f}; solver exception cam0 {cam_exc[0]}/{N} cam1 {cam_exc[1]}/{N}; "
              f"RMSE<2 only {cam_rm[0]/N:.2f}/{cam_rm[1]/N:.2f}; both cameras pass first try {pair/N:.2f}; opening center <1 in {np.mean(np.array(oc) < 1):.3f} of {len(oc)} (med {np.median(oc):.2f}, max {np.max(oc):.2f})", flush=True)

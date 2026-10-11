"""Click method (8 CELL corners, 1.5 px per-axis noise), many seeds, with the operator placement error
(+-1 in, +-0.5 in lens, +-2 deg, +-1 deg roll) and also at the nominal pose. Per camera and per pair pass
rates of the NEW gate (RMSE < 2 px and no point > 3 px) and the opening-center error. No image rendering.
Run: PYTHONPATH=. python evidence/refute/dod9_4/click_many.py [nseeds]
"""
import sys
import numpy as np
sys.path.insert(0, "evidence/refute/dod9_2")
import sim as S
from hiveshot import calib, calib_targets as ct

N = int(sys.argv[1]) if len(sys.argv) > 1 else 300
pts8 = np.array([p for _, p in ct.field_reference_points()])
for opt in ("usb", "gopro"):
    for label, kw in (("placement error", {}), ("nominal pose", dict(pos_err=0, ang_err=0, h_err=0, roll_err=0))):
        for sigma in (1.0, 1.5):
            cam_ok = {0: 0, 1: 0}
            cam_rmse = {0: 0, 1: 0}
            cam_all3 = {0: 0, 1: 0}
            pair_ok = 0
            pair_gate_and_1in = 0
            oc = []
            for seed in range(N):
                rng = np.random.default_rng(31000 + seed)
                cams = [S.true_cam(opt, "A", rng, "cam0", **kw), S.true_cam(opt, "B", rng, "cam1", **kw)]
                exts, ok_flags = [], []
                for k, cam in enumerate(cams):
                    u, v = cam.project(pts8)
                    uv = np.c_[u, v] + rng.normal(0, sigma, (8, 2))
                    e = calib.solve_extrinsics_from_points(cam.intr, uv, pts8, f"cam{k}")
                    rep = calib.reprojection_report(cam.intr, e, uv, pts8)
                    per = np.array(rep["per_point_px"])
                    r2, a3 = rep["rmse_px"] < 2, per.max() < 3
                    cam_rmse[k] += r2
                    cam_all3[k] += a3
                    cam_ok[k] += (r2 and a3)
                    ok_flags.append(r2 and a3)
                    exts.append(e)
                t = S.triang_errors(cams, exts, rng, sigma)
                oc.append(t["opening_center"])
                pair_ok += all(ok_flags)
                pair_gate_and_1in += (all(ok_flags) and t["opening_center"] < 1)
            print(f"{opt:6s} {label:16s} sigma {sigma}: per camera gate cam0 {cam_ok[0]/N:.2f} cam1 {cam_ok[1]/N:.2f} "
                  f"(RMSE<2: {cam_rmse[0]/N:.2f}/{cam_rmse[1]/N:.2f}; all<3: {cam_all3[0]/N:.2f}/{cam_all3[1]/N:.2f}); "
                  f"both cams pass gate {pair_ok/N:.2f}; opening center <1in (any) {np.mean(np.array(oc) < 1):.2f} "
                  f"median {np.median(oc):.2f} max {np.max(oc):.2f}", flush=True)

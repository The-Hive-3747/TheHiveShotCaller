r"""Per-point reprojection gate of the click method (8 CELL corners) vs click noise.

For each camera at the recommended pose (usb and gopro options) the 8 CELL opening corners are projected,
Gaussian click noise (sigma per axis, in px) is added, the pose is solved with calib.solve_extrinsics_from_points
(the same call as the app's /api/calib/extrinsics route) and the per-point reprojection errors are measured
with calib.reprojection_report. Reported: fraction of camera-solves that pass each candidate gate. Also a bad-click
case (one corner clicked 15 px away) to show what each gate catches.
Run: PYTHONPATH=. .venv\Scripts\python.exe -I evidence\refute\dod9_click_gate_sim.py [trials]
"""
import json
import sys

import numpy as np

sys.path.insert(0, "tests")
import test_tagkit as T  # noqa: E402

from hiveshot import calib, calib_targets  # noqa: E402

SIGMAS = (0.5, 0.7, 1.0, 1.5, 2.0)


def run(option, trials):
    xyz = np.array([p for _, p in calib_targets.field_reference_points()])
    out = {}
    for sigma in SIGMAS:
        rows = {"all<2": 0, "all<3": 0, "rmse<2": 0, "rmse<2&all<3": 0, "rmse<2&all<4": 0, "n": 0}
        mx = []
        for k in "AB":
            cam = T._vcam(option, k)
            u, v = cam.project(xyz)
            clean = np.c_[u, v]
            for sd in range(trials):
                rng = np.random.default_rng(7000 + sd)
                clicks = clean + rng.normal(0, sigma, clean.shape)
                ext = calib.solve_extrinsics_from_points(cam.intr, clicks, xyz, cam.cam_id)
                rep = calib.reprojection_report(cam.intr, ext, clicks, xyz)
                per = np.array(rep["per_point_px"])
                rows["n"] += 1
                rows["all<2"] += bool(per.max() < 2)
                rows["all<3"] += bool(per.max() < 3)
                rows["rmse<2"] += bool(rep["rmse_px"] < 2)
                rows["rmse<2&all<3"] += bool(rep["rmse_px"] < 2 and per.max() < 3)
                rows["rmse<2&all<4"] += bool(rep["rmse_px"] < 2 and per.max() < 4)
                mx.append(float(per.max()))
        rows["max_point_px_median"] = float(np.median(mx))
        out[str(sigma)] = rows
    # one bad click (15 px off) at sigma 1.0: which gates flag it
    bad = {"all<2": 0, "all<3": 0, "rmse<2": 0, "rmse<2&all<3": 0, "n": 0}
    for k in "AB":
        cam = T._vcam(option, k)
        u, v = cam.project(xyz)
        for sd in range(trials):
            rng = np.random.default_rng(9000 + sd)
            clicks = np.c_[u, v] + rng.normal(0, 1.0, (8, 2))
            clicks[rng.integers(8)] += np.array([15.0, 0.0])
            ext = calib.solve_extrinsics_from_points(cam.intr, clicks, xyz, cam.cam_id)
            rep = calib.reprojection_report(cam.intr, ext, clicks, xyz)
            per = np.array(rep["per_point_px"])
            bad["n"] += 1
            bad["all<2"] += bool(per.max() < 2)
            bad["all<3"] += bool(per.max() < 3)
            bad["rmse<2"] += bool(rep["rmse_px"] < 2)
            bad["rmse<2&all<3"] += bool(rep["rmse_px"] < 2 and per.max() < 3)
    out["bad_click_15px_sigma1.0"] = bad
    return out


if __name__ == "__main__":
    trials = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    print(json.dumps({opt: run(opt, trials) for opt in ("usb", "gopro")}, indent=1))

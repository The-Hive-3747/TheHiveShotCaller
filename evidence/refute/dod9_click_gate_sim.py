r"""Per-point reprojection gate of the click method (8 CELL corners) vs click noise.

For each camera at the recommended pose (usb and gopro options) the 8 CELL opening corners are projected,
Gaussian click noise (sigma per axis, in px) is added, the pose is solved with calib.solve_extrinsics_from_points
(the same call as the app's /api/calib/extrinsics route) and the per-point reprojection errors are measured
with calib.reprojection_report. Reported: fraction of camera-solves that pass each candidate gate. Also a bad-click
case (one corner clicked 15 px away) to show what each gate catches.
Run: PYTHONPATH=. .venv\Scripts\python.exe evidence\refute\dod9_click_gate_sim.py [trials]
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
        rows = {"all<2": 0, "all<3": 0, "rmse<2": 0, "rmse<2&all<3": 0, "rmse<2&all<4": 0, "n": 0,
                "solve_refused": 0}
        mx = []
        for k in "AB":
            cam = T._vcam(option, k)
            u, v = cam.project(xyz)
            clean = np.c_[u, v]
            for sd in range(trials):
                rng = np.random.default_rng(7000 + sd)
                clicks = clean + rng.normal(0, sigma, clean.shape)
                rows["n"] += 1
                try:
                    ext = calib.solve_extrinsics_from_points(cam.intr, clicks, xyz, cam.cam_id)
                except ValueError:                 # the app answers 422 "PnP RANSAC failed"
                    rows["solve_refused"] += 1
                    continue
                rep = calib.reprojection_report(cam.intr, ext, clicks, xyz)
                per = np.array(rep["per_point_px"])
                rows["all<2"] += bool(per.max() < 2)
                rows["all<3"] += bool(per.max() < 3)
                rows["rmse<2"] += bool(rep["rmse_px"] < 2)
                rows["rmse<2&all<3"] += bool(rep["rmse_px"] < 2 and per.max() < 3)
                rows["rmse<2&all<4"] += bool(rep["rmse_px"] < 2 and per.max() < 4)
                mx.append(float(per.max()))
        rows["max_point_px_median"] = float(np.median(mx)) if mx else None
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
            bad["n"] += 1
            try:
                ext = calib.solve_extrinsics_from_points(cam.intr, clicks, xyz, cam.cam_id)
            except ValueError:
                continue
            rep = calib.reprojection_report(cam.intr, ext, clicks, xyz)
            per = np.array(rep["per_point_px"])
            bad["all<2"] += bool(per.max() < 2)
            bad["all<3"] += bool(per.max() < 3)
            bad["rmse<2"] += bool(rep["rmse_px"] < 2)
            bad["rmse<2&all<3"] += bool(rep["rmse_px"] < 2 and per.max() < 3)
    out["bad_click_15px_sigma1.0"] = bad
    return out


def center_error(option, trials):
    """Opening-center triangulation error (in) when BOTH cameras are solved from noisy clicks."""
    from hiveshot import field

    xyz = np.array([p for _, p in calib_targets.field_reference_points()])
    centre, _ = field.cell_opening_plane("red", "audience", field.CALIBRATION_STATE["red"])
    out = {}
    cams = {k: T._vcam(option, k) for k in "AB"}
    proj = {k: np.c_[cams[k].project(xyz)] for k in "AB"}
    uvc = {k: np.c_[cams[k].project(np.array([centre]))] for k in "AB"}
    for sigma in SIGMAS:
        errs = []
        for sd in range(trials):
            rng = np.random.default_rng(7000 + sd)
            ext = {}
            for k in "AB":
                try:
                    ext[k] = calib.solve_extrinsics_from_points(
                        cams[k].intr, proj[k] + rng.normal(0, sigma, proj[k].shape), xyz, cams[k].cam_id)
                except ValueError:
                    break
            if len(ext) < 2:
                continue
            est, _ = calib.triangulate(cams["A"].intr, ext["A"], uvc["A"], cams["B"].intr, ext["B"], uvc["B"])
            errs.append(float(np.linalg.norm(est[0] - centre)))
        out[str(sigma)] = {"n": len(errs), "median_in": float(np.median(errs)), "max_in": float(np.max(errs))}
    return out


if __name__ == "__main__":
    trials = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    res = {opt: run(opt, trials) for opt in ("usb", "gopro")}
    for opt in res:
        res[opt]["opening_center_error_both_cameras"] = center_error(opt, trials)
    print(json.dumps(res, indent=1))

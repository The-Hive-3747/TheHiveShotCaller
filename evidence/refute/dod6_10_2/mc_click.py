"""Monte Carlo of the click method (docs 3B): 8 clicked points per camera with Gaussian click noise (px, full-res).
Uses the app's own solver (calib.solve_extrinsics_from_points / reprojection_report) on the recommended-pose truth cameras.
Acceptance = the guide's rule: RMSE < 0.25 in AND every point < 2 px.  Quality = independent 3D error (independent of clicks)."""
import sys, json
sys.path.insert(0, "evidence/refute/dod6_10_2")
import numpy as np
import simlib as S
from hiveshot import calib, calib_targets as ct, field
t = S.truth_cams("usb")
pts = ct.field_reference_points()
X = np.array([p for _, p in pts])
P = S._trajectory_points(300)
st = field.HiveState("red", "audience")
cen, _ = field.cell_opening_plane("red", "audience", st)
rng = np.random.default_rng(5)
out = {}
for sigma in (0.5, 1, 1.5, 2, 3, 4, 5):
    rows = []
    for trial in range(200):
        ext = {}
        ok_rule = True
        for c in t:
            uv = np.c_[c.project(X)] + rng.normal(0, sigma, (8, 2))
            try:
                e = calib.solve_extrinsics_from_points(c.intr, uv, X, c.cam_id)
            except ValueError:
                ok_rule = False; ext = None; break
            rep = calib.reprojection_report(c.intr, e, uv, X)
            if not (e.rmse_in < 0.25 and max(rep["per_point_px"]) < 2.0):
                ok_rule = False
            ext[c.cam_id] = e
        if ext is None:
            rows.append(dict(solve_fail=True)); continue
        intr = {c.cam_id: c.intr for c in t}
        err = []
        uv0 = np.c_[t[0].project(P)]; uv1 = np.c_[t[1].project(P)]
        m = np.ones(len(P), bool)
        for c, uv in ((t[0], uv0), (t[1], uv1)):
            m &= (uv[:, 0] > 0) & (uv[:, 0] < 1920) & (uv[:, 1] > 0) & (uv[:, 1] < 1080)
        a = uv0[m] + rng.normal(0, 0.3, (m.sum(), 2)); b = uv1[m] + rng.normal(0, 0.3, (m.sum(), 2))
        xyz, _r = calib.triangulate(intr["cam0"], ext["cam0"], a, intr["cam1"], ext["cam1"], b)
        e3 = np.linalg.norm(xyz - P[m], axis=1)
        c0 = np.c_[t[0].project(cen)][0]; c1 = np.c_[t[1].project(cen)][0]
        xc, _r = calib.triangulate(intr["cam0"], ext["cam0"], c0, intr["cam1"], ext["cam1"], c1)
        rows.append(dict(rule=ok_rule, cell=float(np.linalg.norm(xc - cen)), mean=float(e3.mean()), p95=float(np.percentile(e3, 95)), mx=float(e3.max())))
    ok = [r for r in rows if not r.get("solve_fail")]
    acc = [r for r in ok if r["rule"]]
    out[sigma] = dict(n=len(rows), solve_fail=len(rows) - len(ok), accepted_by_guide_rule=len(acc),
                      cell_err_median=float(np.median([r["cell"] for r in ok])), cell_err_p95=float(np.percentile([r["cell"] for r in ok], 95)),
                      traj_p95_median=float(np.median([r["p95"] for r in ok])),
                      frac_cell_within_1in=float(np.mean([r["cell"] <= 1.0 for r in ok])),
                      accepted_cell_over_1in=int(sum(r["cell"] > 1.0 for r in acc)),
                      accepted_traj_p95_over_1in=int(sum(r["p95"] > 1.0 for r in acc)))
    print(sigma, json.dumps(out[sigma]))
json.dump(out, open("evidence/refute/dod6_10_2/mc_click.json", "w"), indent=1)

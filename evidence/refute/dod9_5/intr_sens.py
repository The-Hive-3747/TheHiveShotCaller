"""Sensitivity to the intrinsics the app would use (the sims above give the solver the TRUE intrinsics).
The frame is rendered with the true camera; the kit solve and the triangulation use intrinsics with a common focal-length error
e ~ N(0, sigma_f) and a principal-point error N(0, 4 px). Tag mounting 0.25 in / 0.5 deg, placement error as before. 40 seeds per row.
Run: PYTHONPATH=. .venv/Scripts/python.exe evidence/refute/dod9_5/intr_sens.py"""
import sys, dataclasses
src = open("evidence/refute/dod9_5/sim5.py").read().split('if __name__')[0]
exec(src)
for opt in ("usb", "gopro"):
    for sf in (0.0, 0.005, 0.01, 0.02):
        res = []
        for s in range(40):
            rng = np.random.default_rng(9000 + s)
            cams = [S.true_cam(opt, "A", rng, "cam0"), S.true_cam(opt, "B", rng, "cam1")]
            kit_model = tagkit.tag_defs()
            hive = {i: c for i, c in pipeline.calibration_hive_defs().items() if 34 <= i <= 41}
            kit_true = {i: perturb(c, 0.25, 0.5, rng) for i, c in kit_model.items()}
            est = []
            for cam in cams:
                e = rng.normal(0, sf)
                est.append(dataclasses.replace(cam.intr, fx=cam.intr.fx * (1 + e), fy=cam.intr.fy * (1 + e),
                                               cx=cam.intr.cx + rng.normal(0, 4), cy=cam.intr.cy + rng.normal(0, 4)))
            exts, reps, ok = [], [], True
            for k, cam in enumerate(cams):
                img = render(cam, kit_true, hive, s * 7 + k)
                try:
                    ex, inf = calib.solve_extrinsics_from_tags(est[k], img, kit_model, f"cam{k}")
                except ValueError:
                    ok = False; break
                exts.append(ex); reps.append(inf["reprojection_px"])
            if not ok:
                res.append(None); continue
            P = S.PROBES["opening_center"]
            uv = []
            for c in cams:
                u, v = c.project(P); uv.append(np.array([u[0], v[0]]) + rng.normal(0, 0.5, 2))
            X, _ = calib.triangulate(est[0], exts[0], uv[0], est[1], exts[1], uv[1])
            err = float(np.linalg.norm(np.asarray(X).reshape(-1)[:3] - P))
            res.append((max(reps), err))
        good = [r for r in res if r]
        print(f"{opt:6s} focal sigma {sf*100:.1f}% pp 4px: unsolved {len(res)-len(good)}; reproj<2px both {sum(r[0]<2 for r in good)}/{len(res)}; opening<1in {sum(r[1]<1 for r in good)}/{len(res)}; both gates {sum(r[0]<2 and r[1]<1 for r in good)}/{len(res)}; reproj med {np.median([r[0] for r in good]):.2f}; open err med {np.median([r[1] for r in good]):.2f} max {max(r[1] for r in good):.2f}", flush=True)

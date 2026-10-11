"""calibration.md 3A step 5 also says accept only if the RMSE shown is under 0.25 in (kit solve). What does the app show under the
documented tolerance (0.25 in / 0.5 deg, placement error)? 60 seeds per option, app path. Run: PYTHONPATH=. .venv/Scripts/python.exe evidence/refute/dod9_5/rmse_in.py"""
src = open("evidence/refute/dod9_5/sim5.py").read().split('if __name__')[0]
exec(src)
for opt in ("usb", "gopro"):
    for mag, ang in ((0, 0), (0.25, 0.5)):
        R = []
        for s in range(60):
            rng = np.random.default_rng(13000 + s)
            cams = [S.true_cam(opt, "A", rng, "cam0"), S.true_cam(opt, "B", rng, "cam1")]
            model = tagkit.tag_defs()
            true = {i: perturb(c, mag, ang, rng) for i, c in model.items()}
            hive = {i: c for i, c in pipeline.calibration_hive_defs().items() if 34 <= i <= 41}
            for k, cam in enumerate(cams):
                e, inf = solve_app(cam, render(cam, true, hive, s * 7 + k))
                R.append((inf["rmse_in"], inf["reprojection_px"], k))
        for k in (0, 1):
            r = np.array([x[0] for x in R if x[2] == k]); p = np.array([x[1] for x in R if x[2] == k])
            print(f"{opt:6s} mount {mag} in/{ang} deg cam{k}: rmse_in med {np.median(r):.3f} p90 {np.percentile(r,90):.3f} max {r.max():.3f}; <0.25 in {int((r<0.25).sum())}/60; reproj px med {np.median(p):.2f} <2px {int((p<2).sum())}/60", flush=True)

"""What if one card is stuck on 180 deg rotated (the printed TAG number and 'THIS EDGE UP' arrow lie outside the cut line)?
Reprojection and opening-center error with that tag rotated; 20 seeds, mounting 0.25 in/0.5 deg, placement error, Arducam.
Run: PYTHONPATH=. .venv/Scripts/python.exe evidence/refute/dod9_5/rot180.py"""
import sys
src = open("evidence/refute/dod9_5/sim5.py").read().split('if __name__')[0]
exec(src)
for opt in ("usb", "gopro"):
    for rot in (101, 103):
        out = []
        for s in range(20):
            rng = np.random.default_rng(11000 + s)
            cams = [S.true_cam(opt, "A", rng, "cam0"), S.true_cam(opt, "B", rng, "cam1")]
            model = tagkit.tag_defs()
            true = {i: perturb(c, 0.25, 0.5, rng) for i, c in model.items()}
            true[rot] = true[rot][[2, 3, 0, 1]]
            hive = {i: c for i, c in pipeline.calibration_hive_defs().items() if 34 <= i <= 41}
            exts, reps, ok = [], [], True
            for k, cam in enumerate(cams):
                img = render(cam, true, hive, s * 7 + k)
                try:
                    e, inf = solve_app(cam, img)
                except ValueError:
                    ok = False; break
                exts.append(e); reps.append(inf["reprojection_px"])
            if ok:
                tri = S.triang_errors(cams, exts, rng, 0.5)["opening_center"]
                out.append((max(reps), tri))
        print(f"{opt} tag {rot} rotated 180: solved {len(out)}/20; reproj max-of-two med {np.median([o[0] for o in out]):.1f} min {min(o[0] for o in out):.1f}; reproj>4px (app refuses) {sum(o[0]>4 for o in out)}; reproj<2px {sum(o[0]<2 for o in out)}; opening center err med {np.median([o[1] for o in out]):.1f} max {max(o[1] for o in out):.1f}; <1in {sum(o[1]<1 for o in out)}", flush=True)

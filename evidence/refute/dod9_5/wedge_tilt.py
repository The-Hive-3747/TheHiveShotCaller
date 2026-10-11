"""Hand-cut wedge: 2 in x 5.5 in cut to +-0.05 in gives a slope angle error of about +-1.4 deg. Both base cards tilted by d (about the card's bottom
edge, same sense on 102 and 103: one wedge design), d = +-1.5 deg, on top of the documented 0.25 in / 0.5 deg mounting error.
30 seeds per option, app path, placement error as before. Run: PYTHONPATH=. .venv/Scripts/python.exe evidence/refute/dod9_5/wedge_tilt.py"""
src = open("evidence/refute/dod9_5/sim5.py").read().split('if __name__')[0]
exec(src)
def tilt_about_bottom(cor, deg):
    # cor order TL,TR,BR,BL ; bottom edge = BR..BL (corners 2,3) shifted down by the border along the card
    bottom = cor[2:4].mean(0)
    u = cor[0] - cor[3]; u /= np.linalg.norm(u)
    pivot = bottom - 0.5 * u                      # the card's own bottom edge (border below the black square)
    ax = cor[1] - cor[0]; ax /= np.linalg.norm(ax)
    R = cv2.Rodrigues(ax * np.radians(deg))[0]
    return (cor - pivot) @ R.T + pivot
for opt in ("usb", "gopro"):
    for d in (1.5, -1.5):
        out = []
        for s in range(30):
            rng = np.random.default_rng(15000 + s)
            cams = [S.true_cam(opt, "A", rng, "cam0"), S.true_cam(opt, "B", rng, "cam1")]
            model = tagkit.tag_defs()
            true = {i: perturb(c, 0.25, 0.5, rng) for i, c in model.items()}
            for i in (102, 103):
                true[i] = tilt_about_bottom(true[i], d)
            hive = {i: c for i, c in pipeline.calibration_hive_defs().items() if 34 <= i <= 41}
            exts, reps = [], []
            for k, cam in enumerate(cams):
                e, inf = solve_app(cam, render(cam, true, hive, s * 7 + k)); exts.append(e); reps.append(inf["reprojection_px"])
            tri = S.triang_errors(cams, exts, rng, 0.5)["opening_center"]
            out.append((max(reps), tri))
        print(f"{opt:6s} base cards tilted {d:+.1f} deg: reproj<2px both {sum(o[0]<2 for o in out)}/30; opening<1in {sum(o[1]<1 for o in out)}/30; both {sum(o[0]<2 and o[1]<1 for o in out)}/30; open err med {np.median([o[1] for o in out]):.2f} max {max(o[1] for o in out):.2f}", flush=True)

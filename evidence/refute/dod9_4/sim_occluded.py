"""What the documented procedure gives when the blue audience CELL (down in the match-start state) hides
kit tags: A can decode only tag 103 (100 fully, 101 half hidden, 102 outside the picture),
B can decode 101, 102, 103 (100 partly hidden). Scene = those tags only (+ HIVE tags 34-37), solver
and gates as in sim4. Cases: kit only (A needs >= 2 tags: expect failure), mixed route (A clicks 8 CELL
corners at 1.5 px with the new gate, B kit), 30 seeds, 0.25 in / 0.5 deg mounting error.
Run: PYTHONPATH=. python evidence/refute/dod9_4/sim_occluded.py usb|gopro
"""
import sys, json
import numpy as np
sys.path.insert(0, "evidence/refute/dod9_2")
sys.path.insert(0, "evidence/refute/dod9_4")
import sim as S
import sim4
from hiveshot import calib, tagkit, calib_targets as ct

opt = sys.argv[1] if len(sys.argv) > 1 else "usb"
N = 30
VISIBLE = {0: (103,), 1: (101, 102, 103)}
rows = []
pts8 = np.array([p for _, p in ct.field_reference_points()])
for seed in range(N):
    rng = np.random.default_rng(8000 + seed)
    cams = [S.true_cam(opt, "A", rng, "cam0"), S.true_cam(opt, "B", rng, "cam1")]
    kit_model = tagkit.tag_defs()
    up = {i: v for i, v in tagkit.hive_tag_defs().items() if 34 <= i <= 37}
    kit_true = {i: sim4.perturb(c, 0.25, 0.5, rng) for i, c in kit_model.items()}
    dets = []
    for k, cam in enumerate(cams):
        scene = {i: kit_true[i] for i in VISIBLE[k]}
        if k == 1:
            scene.update(up)
        dets.append(calib.detect_apriltags(S.render(cam, scene, seed * 7 + k)))
    r = {"seed": seed}
    # kit-only for A
    try:
        S.solve_noisy(cams[0].intr, dets[0], kit_model, "cam0", rng, 0.5)
        r["A_kit_ok"] = True
    except ValueError as e:
        r["A_kit_ok"] = False
        r["A_kit_err"] = str(e)
    # B kit
    eB, used, rp, mx = S.solve_noisy(cams[1].intr, dets[1], kit_model, "cam1", rng, 0.5)
    r["B"] = {"used": used, "reproj": rp, "pos_err": S.pose_err(eB, cams[1].extr)[0]}
    # A by clicks
    u, v = cams[0].project(pts8)
    uv = np.c_[u, v] + rng.normal(0, 1.5, (8, 2))
    eA = calib.solve_extrinsics_from_points(cams[0].intr, uv, pts8, "cam0")
    rep = calib.reprojection_report(cams[0].intr, eA, uv, pts8)
    r["A_click"] = {"rmse": rep["rmse_px"], "max": rep["max_px"], "pos_err": S.pose_err(eA, cams[0].extr)[0]}
    t = S.triang_errors(cams, [eA, eB], rng, 0.5)
    r["opening_center"] = t["opening_center"]
    rows.append(r)
    print(r, flush=True)
a_fail = sum(not r["A_kit_ok"] for r in rows)
gB = sum(r["B"]["reproj"] < 2 for r in rows)
gA = sum(r["A_click"]["rmse"] < 2 and r["A_click"]["max"] < 3 for r in rows)
oc = np.array([r["opening_center"] for r in rows])
both = sum(r["B"]["reproj"] < 2 and r["A_click"]["rmse"] < 2 and r["A_click"]["max"] < 3 and r["opening_center"] < 1 for r in rows)
print(f"{opt}: A kit solve fails (needs 2 tags, sees only 103): {a_fail}/{N}; B kit (101,102,103) reproj<2: {gB}/{N};"
      f" A click new gate: {gA}/{N}; opening center median {np.median(oc):.2f} max {oc.max():.2f}, <1in {int((oc<1).sum())}/{N};"
      f" mixed route passes every gate on first try: {both}/{N}")
json.dump(rows, open(f"evidence/refute/dod9_4/sim_occluded_{opt}.json", "w"), default=float)

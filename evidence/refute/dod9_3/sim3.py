"""DoD 9 round-3 operator simulation. Run: PYTHONPATH=. python sim3.py usb|gopro
Worlds: 'model' = tags exactly where tagkit says (what the code assumes);
        'real'  = tags 100/101 flat on the REAL (24 deg tilted) CAD logo panel, top edge flush with panel top,
                  centered x=+-12 (the documented taping), tags 102/103 as modeled (leaning on foot bar end).
Mount error: each kit tag displaced by `mag` in (random dir) and tilted `ang` deg (random axis), on top of the world.
"""
import sys, json, time
import numpy as np, cv2
from multiprocessing import Pool
sys.path.insert(0, "evidence/refute/dod9_2")
import sim as S
from hiveshot import calib, tagkit, calib_targets as ct

PANEL_TOP = np.array([1.666, 40.024])
PANEL_BOT = np.array([4.292, 34.125])


def real_panel_corners(sx, size=6.0):
    t = PANEL_TOP - PANEL_BOT
    t = t / np.linalg.norm(t)
    n = np.array([t[1], -t[0]])
    if n[0] < 0:
        n = -n
    up = np.array([0.0, t[0], t[1]])
    nn = np.array([0.0, n[0], n[1]])
    r = np.cross(up, nn)
    h = size / 2
    c = np.array([sx * 12.0, PANEL_TOP[0], PANEL_TOP[1]]) - h * up
    return np.array([c + h * up - h * r, c + h * up + h * r, c - h * up + h * r, c - h * up - h * r])


def perturb(corners, mag, ang_deg, rng):
    if not mag and not ang_deg:
        return corners
    c = corners.mean(axis=0)
    d = rng.normal(size=3)
    d *= mag / np.linalg.norm(d)
    ax = rng.normal(size=3)
    ax /= np.linalg.norm(ax)
    R = cv2.Rodrigues(ax * np.radians(ang_deg))[0]
    return (corners - c) @ R.T + c + d


def one(args):
    seed, opt, world, mag, ang = args
    rng = np.random.default_rng(5000 + seed)
    cams = [S.true_cam(opt, "A", rng, "cam0"), S.true_cam(opt, "B", rng, "cam1")]
    kit_model = tagkit.tag_defs()
    hive = tagkit.hive_tag_defs()
    up = {i: v for i, v in hive.items() if 34 <= i <= 37}
    base = dict(kit_model)
    if world == "real":
        base[100] = real_panel_corners(-1)
        base[101] = real_panel_corners(+1)
    kit_true = {i: perturb(c, mag, ang, rng) for i, c in base.items()}
    scene = {**kit_true, **up}
    res = {"seed": seed}
    dets = []
    for k, cam in enumerate(cams):
        im = S.render(cam, scene, seed * 7 + k)
        dets.append(calib.detect_apriltags(im))
    res["detected"] = [sorted(d["id"] for d in dets[k]) for k in range(2)]
    exts, info, ok = [], [], True
    for k, cam in enumerate(cams):
        try:
            e, used, rp, mx = S.solve_noisy(cam.intr, dets[k], kit_model, f"cam{k}", rng, 0.5)
            exts.append(e)
            pe, ae = S.pose_err(e, cam.extr)
            info.append({"used": used, "reproj_px": rp, "max_px": mx, "pos_err_in": pe, "rot_err_deg": ae})
        except ValueError as ex:
            ok = False
            info.append({"fail": str(ex)})
            exts.append(None)
    res["kit"] = {"cams": info}
    if ok:
        res["kit"]["tri"] = S.triang_errors(cams, exts, rng, 0.5)
        da = {d["id"]: d["corners"] for d in dets[0] if d["id"] in up}
        db = {d["id"]: d["corners"] for d in dets[1] if d["id"] in up}
        both = sorted(set(da) & set(db))
        res["kit"]["oos_ids"] = both
        if both:
            ua = np.vstack([np.asarray(da[i], float).reshape(4, 2) for i in both]) + rng.normal(0, .5, (4 * len(both), 2))
            ub = np.vstack([np.asarray(db[i], float).reshape(4, 2) for i in both]) + rng.normal(0, .5, (4 * len(both), 2))
            X, _ = calib.triangulate(cams[0].intr, exts[0], ua, cams[1].intr, exts[1], ub)
            exp = np.vstack([up[i] for i in both])
            res["kit"]["oos_max_in"] = float(np.linalg.norm(X - exp, axis=1).max())
        ids = sorted(set(info[0]["used"]) & set(info[1]["used"]))
        sd = [{d["id"]: d["corners"] for d in dets[k]} for k in (0, 1)]
        if ids:
            ua = np.vstack([np.asarray(sd[0][i], float).reshape(4, 2) for i in ids])
            ub = np.vstack([np.asarray(sd[1][i], float).reshape(4, 2) for i in ids])
            X, _ = calib.triangulate(cams[0].intr, exts[0], ua, cams[1].intr, exts[1], ub)
            exp = np.vstack([kit_model[i] for i in ids])
            res["kit"]["insample_max_in"] = float(np.linalg.norm(X - exp, axis=1).max())
            tru = np.vstack([base[i] for i in ids])
            res["kit"]["insample_vs_true_max_in"] = float(np.linalg.norm(X - tru, axis=1).max())
    pts8 = np.array([p for _, p in ct.field_reference_points()])
    exts, info, ok = [], [], True
    for k, cam in enumerate(cams):
        u, v = cam.project(pts8)
        uv = np.c_[u, v] + rng.normal(0, 1.5, (8, 2))
        try:
            e = calib.solve_extrinsics_from_points(cam.intr, uv, pts8, f"cam{k}")
            rep = calib.reprojection_report(cam.intr, e, uv, pts8)
            pe, ae = S.pose_err(e, cam.extr)
            info.append({"reproj_px": rep["rmse_px"], "max_px": rep["max_px"], "pos_err_in": pe, "rot_err_deg": ae})
            exts.append(e)
        except Exception as ex:
            ok = False
            info.append({"fail": str(ex)})
            exts.append(None)
    res["click8"] = {"cams": info}
    if ok:
        res["click8"]["tri"] = S.triang_errors(cams, exts, rng, 1.5)
    return res


def st(v):
    v = [x for x in v if x is not None]
    if not v:
        return "n/a"
    a = np.array(v)
    return f"med {np.median(a):.2f} p90 {np.percentile(a, 90):.2f} max {a.max():.2f}"


def summarize(rs, label):
    L = [f"### {label} (seeds={len(rs)})"]
    for m in ("kit", "click8"):
        solved = [r for r in rs if "tri" in r[m]]
        L.append(f"- {m}: both cameras solved {len(solved)}/{len(rs)}")
        for k in (0, 1):
            cs = [r[m]["cams"][k] for r in rs if "fail" not in r[m]["cams"][k]]
            extra = f"; tags used median {np.median([len(c['used']) for c in cs]):.0f}" if cs and "used" in cs[0] else ""
            L.append(f"    cam{k}: reproj px {st([c['reproj_px'] for c in cs])}; <2px {sum(c['reproj_px'] < 2 for c in cs)}/{len(rs)}; "
                     f"pos err in {st([c['pos_err_in'] for c in cs])}; rot deg {st([c['rot_err_deg'] for c in cs])}{extra}")
        g2 = [r for r in solved if all(r[m]["cams"][k]["reproj_px"] < 2 for k in (0, 1))]
        L.append(f"    GATE reproj<2px both cameras: {len(g2)}/{len(rs)}")
        for p in ("opening_center", "tag_row_center", "flight_rms"):
            v = [r[m]["tri"][p] for r in solved if p in r[m]["tri"]]
            L.append(f"    {p} err in: {st(v)}; <1 in {sum(x < 1 for x in v)}/{len(rs)}")
        both = [r for r in solved if r[m]["tri"]["opening_center"] < 1 and all(r[m]["cams"][k]["reproj_px"] < 2 for k in (0, 1))]
        L.append(f"    BOTH gates (2px each cam AND opening center<1in): {len(both)}/{len(rs)}")
    kit = [r["kit"] for r in rs if "tri" in r["kit"]]
    n_oos = sum(1 for k in kit if k.get("oos_ids"))
    L.append(f"- kit out-of-sample HIVE-tag check possible (a HIVE tag decoded in BOTH cameras): {n_oos}/{len(rs)}")
    c0 = np.mean([len([i for i in r["detected"][0] if i < 100]) for r in rs])
    c1 = np.mean([len([i for i in r["detected"][1] if i < 100]) for r in rs])
    L.append(f"    mean HIVE tags decoded per camera: cam0 {c0:.2f}, cam1 {c1:.2f}")
    v = [k["oos_max_in"] for k in kit if "oos_max_in" in k]
    L.append(f"    oos max HIVE-tag corner error in: {st(v)}; <1 in {sum(x < 1 for x in v)}/{len(v)}")
    v = [k["insample_max_in"] for k in kit if "insample_max_in" in k]
    L.append(f"    in-sample kit-tag check vs MODEL (app fallback): {st(v)}; <1in {sum(x < 1 for x in v)}/{len(v)}")
    v = [k["insample_vs_true_max_in"] for k in kit if "insample_vs_true_max_in" in k]
    L.append(f"    same triangulated points vs TRUE tag positions: {st(v)}")
    k0 = np.mean([len([i for i in r["detected"][0] if i >= 100]) for r in rs])
    k1 = np.mean([len([i for i in r["detected"][1] if i >= 100]) for r in rs])
    L.append(f"    kit tags decoded: cam0 {k0:.2f}, cam1 {k1:.2f}")
    return "\n".join(L)


if __name__ == "__main__":
    opt = sys.argv[1] if len(sys.argv) > 1 else "usb"
    cases = {"model_exact": ("model", 0, 0), "model_0.25in_0.5deg": ("model", 0.25, 0.5),
             "real_exact": ("real", 0, 0), "real_0.25in_0.5deg": ("real", 0.25, 0.5)}
    out, text = {}, []
    t0 = time.time()
    with Pool(8) as pool:
        for cn, (w, m, a) in cases.items():
            rs = pool.map(one, [(s, opt, w, m, a) for s in range(30)])
            out[cn] = rs
            text.append(summarize(rs, f"{opt} / {cn}"))
            print(text[-1], flush=True)
            print("elapsed", time.time() - t0, flush=True)
    json.dump(out, open(f"evidence/refute/dod9_3/sim3_{opt}.json", "w"), default=float)
    open(f"evidence/refute/dod9_3/sim3_{opt}.txt", "w").write("\n\n".join(text))

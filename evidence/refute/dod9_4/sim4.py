"""DoD 9 round-4 operator simulation, single process.
Run: PYTHONPATH=. python evidence/refute/dod9_4/sim4.py usb|gopro [nseeds] [cases]
World = the CURRENT tagkit model (tags 100/101 on the real panel plane per field.logo_panel_face,
102/103 on the foot bar end).
Cases:
  exact        : tags exactly at the model
  mount_0.25   : each kit tag displaced 0.25 in (random dir) and tilted 0.5 deg (random axis)
                 [the documented tolerance]
  border_0.25  : mount_0.25 PLUS base tags 102/103 raised 0.5 in along the slope (the black square's
                 bottom edge sits on the card's white border, the card stands on the tile): an
                 ambiguity in "bottom edge on the tile"
Placement error: +-1 in x/y, +-0.5 in lens, +-2 deg yaw/pitch, +-1 deg roll. Corner noise 0.5 px.
Click: 8 CELL corners, 1.5 px noise.
"""
import sys, json, time
import numpy as np, cv2
sys.path.insert(0, "evidence/refute/dod9_2")
import sim as S
from hiveshot import calib, tagkit, calib_targets as ct


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


def one(seed, opt, world, mag, ang):
    rng = np.random.default_rng(8000 + seed)
    cams = [S.true_cam(opt, "A", rng, "cam0"), S.true_cam(opt, "B", rng, "cam1")]
    kit_model = tagkit.tag_defs()
    hive = tagkit.hive_tag_defs()
    up = {i: v for i, v in hive.items() if 34 <= i <= 37}
    base = dict(kit_model)
    if world == "border":
        u = np.array([0.0, -np.sin(np.radians(20)), np.cos(np.radians(20))])
        for i in (102, 103):
            base[i] = base[i] + 0.5 * u
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
        if ids:
            sd = [{d["id"]: d["corners"] for d in dets[k]} for k in (0, 1)]
            ua = np.vstack([np.asarray(sd[0][i], float).reshape(4, 2) for i in ids])
            ub = np.vstack([np.asarray(sd[1][i], float).reshape(4, 2) for i in ids])
            X, _ = calib.triangulate(cams[0].intr, exts[0], ua, cams[1].intr, exts[1], ub)
            res["kit"]["insample_max_in"] = float(np.linalg.norm(X - np.vstack([kit_model[i] for i in ids]), axis=1).max())
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
        if m == "click8":
            gn = [r for r in solved if all(r[m]["cams"][k]["reproj_px"] < 2 and r[m]["cams"][k]["max_px"] < 3 for k in (0, 1))]
            L.append(f"    NEW GATE (RMSE<2 and no point>3 px, both cameras): {len(gn)}/{len(rs)}")
            ga = sum(1 for r in solved for k in (0, 1) if r[m]["cams"][k]["reproj_px"] < 2 and r[m]["cams"][k]["max_px"] < 3)
            L.append(f"    NEW GATE per camera: {ga}/{2 * len(rs)}")
            gl = [r for r in gn if r[m]["tri"]["opening_center"] < 1]
            L.append(f"    NEW GATE both cams AND opening center<1in: {len(gl)}/{len(rs)}")
        v = [r[m]["tri"]["opening_center"] for r in solved]
        L.append(f"    opening_center err in: {st(v)}; <1 in {sum(x < 1 for x in v)}/{len(rs)}")
        both = [r for r in solved if r[m]["tri"]["opening_center"] < 1 and all(r[m]["cams"][k]["reproj_px"] < 2 for k in (0, 1))]
        L.append(f"    BOTH gates (2px each cam AND opening center<1in): {len(both)}/{len(rs)}")
    kit = [r["kit"] for r in rs if "tri" in r["kit"]]
    L.append(f"- kit out-of-sample HIVE-tag check possible: {sum(1 for k in kit if k.get('oos_ids'))}/{len(rs)}")
    v = [k["oos_max_in"] for k in kit if "oos_max_in" in k]
    L.append(f"    oos max HIVE-tag corner error in: {st(v)}; <1 in {sum(x < 1 for x in v)}/{len(v)}")
    v = [k["insample_max_in"] for k in kit if "insample_max_in" in k]
    L.append(f"    in-sample kit-tag check vs MODEL: {st(v)}; <1in {sum(x < 1 for x in v)}/{len(v)}")
    c0 = np.mean([len([i for i in r["detected"][0] if i >= 100]) for r in rs])
    c1 = np.mean([len([i for i in r["detected"][1] if i >= 100]) for r in rs])
    h0 = np.mean([len([i for i in r["detected"][0] if i < 100]) for r in rs])
    h1 = np.mean([len([i for i in r["detected"][1] if i < 100]) for r in rs])
    L.append(f"    kit tags decoded: cam0 {c0:.2f}, cam1 {c1:.2f}; HIVE tags decoded cam0 {h0:.2f}, cam1 {h1:.2f}")
    return "\n".join(L)


if __name__ == "__main__":
    opt = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    cases = {"exact": ("model", 0, 0), "mount_0.25": ("model", 0.25, 0.5), "border_0.25": ("border", 0.25, 0.5)}
    tag = ""
    if len(sys.argv) > 3:
        cases = {k: v for k, v in cases.items() if k in sys.argv[3].split(",")}
        tag = "_" + sys.argv[3].replace(",", "_")
    out, text, t0 = {}, [], time.time()
    for cn, (w, m, a) in cases.items():
        rs = [one(s, opt, w, m, a) for s in range(n)]
        out[cn] = rs
        text.append(summarize(rs, f"{opt} / {cn}"))
        print(text[-1], flush=True)
        print("elapsed", round(time.time() - t0), flush=True)
    json.dump(out, open(f"evidence/refute/dod9_4/sim4_{opt}{tag}.json", "w"), default=float)
    open(f"evidence/refute/dod9_4/sim4_{opt}{tag}.txt", "w").write("\n\n".join(text))

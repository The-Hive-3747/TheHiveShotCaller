"""DoD 9 round 5 operator simulation (single process, 30 seeds per case, both options).
Run: PYTHONPATH=. .venv/Scripts/python.exe evidence/refute/dod9_5/sim5.py usb|gopro [nseeds]

World = CALIBRATION_STATE (both audience CELLs up): kit tags 100-103 at the current tagkit model,
HIVE tags of both alliances (calibration_hive_defs, 3.25 in) rendered too. A tag is NOT rendered if an
independent test says a CELL body (convex hull of field.cell_body_corners) or the frame hides any
sample point of it (occ5.py showed none is hidden at the documented spots; the filter is kept so that
the placement error cannot silently re-introduce an occluder).
Cameras: documented spot with uniform placement error +-1 in x/y, +-0.5 in lens height, +-2 deg yaw/pitch,
+-1 deg roll (sim.true_cam). Render 1920x1080, 2 gray-level noise, 3x3 blur; the card has the REAL 0.5 in
white border (not the 0.75 in halo of earlier sims), exact 3-D card quad projected.
Cases (tag mounting error applied to the true tags, solver uses the model):
  exact       : none
  mount_0.25  : each kit tag displaced 0.25 in (random dir) and tilted 0.5 deg (random axis) [documented tolerance]
  card_t0.2   : mount_0.25 PLUS base tags 102/103 shifted 0.2 in along their face normal (printed face sits one
                foam-core thickness in front of a card whose back rests on the bar edge)
Kit solve, source kit, two paths: (a) 'app' = calib.solve_extrinsics_from_tags on the rendered image
(exactly the app path, detector corner noise only), (b) 'n0.5' = detections + 0.5 px Gaussian corner noise,
solve_extrinsics_from_points (S.solve_noisy). Gates per run: reprojection < 2 px in both cameras, and the
triangulated up-CELL opening center within 1 in of CAD (0.5 px noise on the projections). Also reported:
out-of-sample check (HIVE tags 34-41 seen by both cameras, triangulated, max corner error vs computed) and the
click method (8 CELL corners at 1.5 px) against the gate RMSE < 2 px and no point > 3 px.
"""
import json
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, "evidence/refute/dod9_2")
import sim as S  # noqa: E402

from hiveshot import calib, field, tagkit  # noqa: E402
from hiveshot import calib_targets as ct  # noqa: E402
from hiveshot import pipeline  # noqa: E402

W, H = S.W, S.H
BORDER = tagkit.CARD_BORDER_IN


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


def card_quad(cor, border):
    c = cor.mean(axis=0)
    r = cor[1] - cor[0]
    r /= np.linalg.norm(r)
    u = cor[0] - cor[3]
    u /= np.linalg.norm(u)
    h = np.linalg.norm(cor[1] - cor[0]) / 2 + border
    return np.array([c + h * u - h * r, c + h * u + h * r, c - h * u + h * r, c - h * u - h * r])


def render(cam, tags, hive, seed):
    img = np.full((H, W, 3), 110, np.uint8)
    n = 400
    s = np.float32([[0, 0], [n, 0], [n, n], [0, n]])
    for tid, c in tags.items():
        u, v = cam.project(card_quad(c, BORDER))
        cv2.fillConvexPoly(img, np.c_[u, v].astype(np.int32), (255, 255, 255))
    for tid, c in hive.items():
        u, v = cam.project(c)
        q = np.c_[u, v]
        ctr = q.mean(0)
        cv2.fillConvexPoly(img, (ctr + (q - ctr) * 1.25).astype(np.int32), (255, 255, 255))
    allt = {**hive, **tags}
    for tid, c in allt.items():
        u, v = cam.project(c)
        Hm = cv2.getPerspectiveTransform(s, np.c_[u, v].astype(np.float32))
        wp = cv2.warpPerspective(tagkit.render_marker(tid, n), Hm, (W, H), flags=cv2.INTER_AREA, borderValue=0)
        mk = cv2.warpPerspective(np.full((n, n), 255, np.uint8), Hm, (W, H), borderValue=0) > 250
        img[mk] = wp[mk][:, None]
    rng = np.random.default_rng(seed)
    img = np.clip(img.astype(np.float32) + rng.normal(0, 2.0, img.shape), 0, 255)
    return cv2.GaussianBlur(img.astype(np.uint8), (3, 3), 0.6)


# ------------------------------ occlusion filter (independent hull + frame legs/bars)
sys.path.insert(0, "evidence/refute/dod9_5")
from scipy.spatial import Delaunay  # noqa: E402

_HULLS = [Delaunay(field.cell_body_corners(al, wh, field.CALIBRATION_STATE[al]))
          for al in field.ALLIANCES for wh in field.CELLS]


def hidden(cam_pos, corners):
    c = corners.mean(axis=0)
    pts = np.vstack([c + 0.9 * (corners - c), c[None]])
    for p in pts:
        d = p - cam_pos
        L = np.linalg.norm(d)
        t = np.linspace(0, (L - 0.3) / L, 600)[:, None]
        s = cam_pos + t * d
        if any((h.find_simplex(s) >= 0).any() for h in _HULLS):
            return True
    return False


def solve_app(cam, img):
    kit_model = tagkit.tag_defs()
    return calib.solve_extrinsics_from_tags(cam.intr, img, kit_model, cam.intr.cam_id)


def gates_from(cams, exts, rng, reps):
    tri = S.triang_errors(cams, exts, rng, 0.5)
    ok2 = all(r < 2.0 for r in reps)
    return {"tri": tri, "reproj_lt2": bool(ok2), "open_lt1": bool(tri["opening_center"] < 1.0),
            "both": bool(ok2 and tri["opening_center"] < 1.0)}


def one(seed, opt, mag, ang, card_t):
    rng = np.random.default_rng(5000 + seed)
    cams = [S.true_cam(opt, "A", rng, "cam0"), S.true_cam(opt, "B", rng, "cam1")]
    kit_model = tagkit.tag_defs()
    hive = {i: c for i, c in pipeline.calibration_hive_defs().items() if 34 <= i <= 41}   # audience CELLs up (face the cameras)
    kit_true = {i: perturb(c, mag, ang, rng) for i, c in kit_model.items()}
    if card_t:
        for i in (102, 103):
            n = tagkit.tag_normal_xyz(i)
            kit_true[i] = kit_true[i] + card_t * n
    res = {"seed": seed}
    dets, imgs = [], []
    for k, cam in enumerate(cams):
        pos = -cv2.Rodrigues(np.array(cam.extr.rvec))[0].T @ np.array(cam.extr.tvec)
        vis_k = {i: c for i, c in kit_true.items() if not hidden(pos, c)}
        vis_h = dict(hive)   # own CELL body surrounds the sticker; other-CELL clearance checked in occ5b.py
        res.setdefault("hidden_kit", []).append(sorted(set(kit_true) - set(vis_k)))
        img = render(cam, vis_k, vis_h, seed * 7 + k)
        imgs.append(img)
        dets.append(calib.detect_apriltags(img))
    res["detected"] = [sorted(d["id"] for d in dets[k]) for k in range(2)]
    # (a) app path
    for path in ("app", "n0.5"):
        exts, reps, info, ok = [], [], [], True
        for k, cam in enumerate(cams):
            try:
                if path == "app":
                    e, inf = solve_app(cam, imgs[k])
                    used, rp, mx = inf["tags_used"], inf["reprojection_px"], inf["max_corner_px"]
                else:
                    e, used, rp, mx = S.solve_noisy(cam.intr, dets[k], kit_model, f"cam{k}", rng, 0.5)
                pe, ae = S.pose_err(e, cam.extr)
                exts.append(e)
                reps.append(rp)
                info.append({"used": used, "reproj_px": rp, "max_px": mx, "pos_err_in": pe, "rot_err_deg": ae})
            except ValueError as ex:
                ok = False
                info.append({"fail": str(ex)})
                exts.append(None)
                reps.append(99.0)
        r = {"cams": info, "solved": ok}
        if ok:
            r.update(gates_from(cams, exts, rng, reps))
            # out-of-sample check with the HIVE tags both cameras decode
            hd = {i for i in hive}
            da = {d["id"]: d["corners"] for d in dets[0] if d["id"] in hd}
            db = {d["id"]: d["corners"] for d in dets[1] if d["id"] in hd}
            both = sorted(set(da) & set(db))
            r["oos_ids"] = both
            if both:
                ua = np.vstack([np.asarray(da[i], float).reshape(4, 2) for i in both]) + rng.normal(0, .5, (4 * len(both), 2))
                ub = np.vstack([np.asarray(db[i], float).reshape(4, 2) for i in both]) + rng.normal(0, .5, (4 * len(both), 2))
                X, _ = calib.triangulate(cams[0].intr, exts[0], ua, cams[1].intr, exts[1], ub)
                r["oos_max_in"] = float(np.linalg.norm(X - np.vstack([hive[i] for i in both]), axis=1).max())
        res[path] = r
    # click method, 1.5 px
    pts8 = np.array([p for _, p in ct.field_reference_points()])
    exts, info, ok = [], [], True
    for k, cam in enumerate(cams):
        u, v = cam.project(pts8)
        uv = np.c_[u, v] + rng.normal(0, 1.5, (8, 2))
        try:
            e = calib.solve_extrinsics_from_points(cam.intr, uv, pts8, f"cam{k}")
            rep = calib.reprojection_report(cam.intr, e, uv, pts8)
            pe, ae = S.pose_err(e, cam.extr)
            info.append({"rmse_px": rep["rmse_px"], "max_px": rep["max_px"], "pos_err_in": pe, "rot_err_deg": ae,
                         "gate": bool(rep["rmse_px"] < 2 and rep["max_px"] < 3)})
            exts.append(e)
        except Exception as ex:  # noqa: BLE001
            ok = False
            info.append({"fail": str(ex)})
            exts.append(None)
    res["click"] = {"cams": info, "solved": ok}
    if ok:
        res["click"]["tri"] = S.triang_errors(cams, exts, rng, 1.5)["opening_center"]
    return res


def tally(rs, label):
    L = [f"### {label}  seeds={len(rs)}"]
    L.append(f"  detected kit ids cam0 (counts): " + str({i: sum(i in r['detected'][0] for r in rs) for i in (100, 101, 102, 103)})
             + "  cam1: " + str({i: sum(i in r['detected'][1] for r in rs) for i in (100, 101, 102, 103)})
             + f"  | hidden-by-occluder runs: {sum(1 for r in rs if any(r['hidden_kit']))}")
    for path in ("app", "n0.5"):
        sl = [r[path] for r in rs]
        solved = [x for x in sl if x["solved"]]
        L.append(f"  kit solve [{path}]: both cameras solved {len(solved)}/{len(rs)}")
        for k in (0, 1):
            cs = [x["cams"][k] for x in solved]
            if cs:
                rp = np.array([c["reproj_px"] for c in cs])
                pe = np.array([c["pos_err_in"] for c in cs])
                ae = np.array([c["rot_err_deg"] for c in cs])
                nt = np.array([len(c["used"]) for c in cs])
                L.append(f"    cam{k}: reproj px med {np.median(rp):.2f} max {rp.max():.2f}, <2px {int((rp < 2).sum())}/{len(rs)}; "
                         f"pos err in med {np.median(pe):.2f} max {pe.max():.2f}; rot deg med {np.median(ae):.2f} max {ae.max():.2f}; tags used med {np.median(nt):.0f} min {nt.min()}")
        L.append(f"    reproj<2px both cameras: {sum(x['reproj_lt2'] for x in solved)}/{len(rs)}")
        oc = np.array([x["tri"]["opening_center"] for x in solved])
        if len(oc):
            L.append(f"    opening center err in: med {np.median(oc):.2f} p90 {np.percentile(oc, 90):.2f} max {oc.max():.2f}; <1 in {int((oc < 1).sum())}/{len(rs)}")
        L.append(f"    BOTH GATES (2 px both cams AND opening center < 1 in): {sum(x['both'] for x in solved)}/{len(rs)}")
        oos = [x["oos_max_in"] for x in solved if "oos_max_in" in x]
        L.append(f"    out-of-sample HIVE-tag check possible {len(oos)}/{len(rs)}; max corner err in med {np.median(oos) if oos else float('nan'):.2f} max {max(oos) if oos else float('nan'):.2f}; <1 in {sum(o < 1 for o in oos)}/{len(oos)}")
    cl = [r["click"] for r in rs]
    cs = [r["click"] for r in rs if r["click"]["solved"]]
    g = [c["gate"] for r in cs for c in r["cams"]]
    both = [all(c["gate"] for c in r["cams"]) for r in cs]
    rm = [c["rmse_px"] for r in cs for c in r["cams"]]
    tri = [r["tri"] for r in cs]
    L.append(f"  click method 1.5 px: per-camera gate passed {sum(g)}/{len(g)}; both on first try {sum(both)}/{len(cs)}; RMSE<2 only {sum(x < 2 for x in rm)}/{len(rm)}; "
             f"opening center err med {np.median(tri):.2f} max {np.max(tri):.2f}, <1 in {sum(t < 1 for t in tri)}/{len(tri)}")
    return "\n".join(L)


if __name__ == "__main__":
    opt = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    cases = {"exact": (0, 0, 0), "mount_0.25": (0.25, 0.5, 0), "card_t0.2": (0.25, 0.5, 0.2)}
    out, text, t0 = {}, [], time.time()
    for cn, (m, a, t) in cases.items():
        rs = [one(s, opt, m, a, t) for s in range(n)]
        out[cn] = rs
        text.append(tally(rs, f"{opt} / {cn}"))
        print(text[-1], flush=True)
        print("elapsed", round(time.time() - t0), flush=True)
    json.dump(out, open(f"evidence/refute/dod9_5/sim5_{opt}.json", "w"), default=float)
    open(f"evidence/refute/dod9_5/sim5_{opt}.txt", "w").write("\n\n".join(text))

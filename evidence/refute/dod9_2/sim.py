"""DoD 9 round-2 operator simulation (pure library). Run: PYTHONPATH=. python sim.py usb|gopro"""
import sys, json, math, time
import numpy as np, cv2
from multiprocessing import Pool
from hiveshot import placement as pl, calib, tagkit, field, calib_targets as ct
from hiveshot import field_constants as fc
from hiveshot.synth import VirtualCamera
from hiveshot.models import CameraExtrinsics

W, H = 1920, 1080
CTR = np.array(field.cell_opening_plane("red", "audience", field.HiveState())[0])
ROWC = np.array([fc.RED_HIVE_X, *fc.HIVE_TAG_ROW_CENTER_UP])
PROBES = {"opening_center": CTR, "tag_row_center": ROWC}


def rot_about_axis(R, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    Rz = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])
    return Rz @ R


def true_cam(opt, k, rng, cam_id, pos_err=1.0, ang_err=2.0, h_err=0.5, roll_err=1.0):
    c = pl.recommend(opt)["cameras"][k]
    pos = np.array(c["pos"], float) + [rng.uniform(-pos_err, pos_err), rng.uniform(-pos_err, pos_err),
                                       rng.uniform(-h_err, h_err)]
    yaw, pitch = pl.aim_angles(c)
    yaw += rng.uniform(-ang_err, ang_err)
    pitch += rng.uniform(-ang_err, ang_err)
    y, p = math.radians(yaw), math.radians(pitch)
    d = np.array([math.cos(p) * math.cos(y), math.cos(p) * math.sin(y), math.sin(p)])
    cam = VirtualCamera.look_at(cam_id, pos, pos + 100 * d, W, H, fx=pl.hfov_to_fx(c["hfov_deg"], W))
    R = cv2.Rodrigues(np.array(cam.extr.rvec))[0]
    R2 = rot_about_axis(R, rng.uniform(-roll_err, roll_err))
    t2 = -R2 @ pos
    ext = CameraExtrinsics(cam_id, tuple(float(x) for x in cv2.Rodrigues(R2)[0].ravel()),
                           tuple(float(x) for x in t2))
    return VirtualCamera(cam.intr, ext)


def render(cam, tags, seed):
    img = np.full((H, W, 3), 110, np.uint8)
    n = 400
    s = np.float32([[0, 0], [n, 0], [n, n], [0, n]])
    for c in tags.values():
        u, v = cam.project(c)
        q = np.c_[u, v]
        ctr = q.mean(0)
        cv2.fillConvexPoly(img, (ctr + (q - ctr) * 1.25).astype(np.int32), (255, 255, 255))
    for tid, c in tags.items():
        u, v = cam.project(c)
        Hm = cv2.getPerspectiveTransform(s, np.c_[u, v].astype(np.float32))
        wp = cv2.warpPerspective(tagkit.render_marker(tid, n), Hm, (W, H), flags=cv2.INTER_AREA, borderValue=0)
        mk = cv2.warpPerspective(np.full((n, n), 255, np.uint8), Hm, (W, H), borderValue=0) > 250
        img[mk] = wp[mk][:, None]
    rng = np.random.default_rng(seed)
    img = np.clip(img.astype(np.float32) + rng.normal(0, 2.0, img.shape), 0, 255)
    return cv2.GaussianBlur(img.astype(np.uint8), (3, 3), 0.6)


def pose_err(est, true):
    Re = cv2.Rodrigues(np.array(est.rvec))[0]
    Rt = cv2.Rodrigues(np.array(true.rvec))[0]
    pe = -Re.T @ np.array(est.tvec)
    pt = -Rt.T @ np.array(true.tvec)
    ang = math.degrees(math.acos(np.clip((np.trace(Re.T @ Rt) - 1) / 2, -1, 1)))
    return float(np.linalg.norm(pe - pt)), ang


def solve_noisy(intr, dets, defs, cam_id, rng, noise_px, min_tags=2):
    seen = {}
    for d in dets:
        if d["id"] in defs and d["id"] not in seen:
            seen[d["id"]] = d["corners"]
    used = sorted(seen)
    if len(used) < min_tags:
        raise ValueError(f"only tags {used}")
    img = np.vstack([seen[t] for t in used]) + rng.normal(0, noise_px, (4 * len(used), 2))
    fld = np.vstack([defs[t] for t in used])
    ext = calib.solve_extrinsics_from_points(intr, img, fld, cam_id, use_ransac=False)
    rep = calib.reprojection_report(intr, ext, img, fld)
    return ext, used, rep["rmse_px"], rep["max_px"]


_TRAJ = None


def traj_points():
    global _TRAJ
    if _TRAJ is None:
        _TRAJ = pl._stack(pl.sample_trajectories())[::4]
    return _TRAJ


def triang_errors(cams, exts, rng, noise_px):
    out = {}
    pts = traj_points()
    m = np.ones(len(pts), bool)
    uvs = []
    for c in cams:
        u, v = c.project(pts)
        m &= (u > 20) & (u < W - 20) & (v > 20) & (v < H - 20) & (c.depth(pts) > 0)
        uvs.append(np.c_[u, v])
    if m.sum() >= 5:
        ua = uvs[0][m] + rng.normal(0, noise_px, (m.sum(), 2))
        ub = uvs[1][m] + rng.normal(0, noise_px, (m.sum(), 2))
        X, _ = calib.triangulate(cams[0].intr, exts[0], ua, cams[1].intr, exts[1], ub)
        e = np.linalg.norm(X - pts[m], axis=1)
        out["flight_rms"] = float(np.sqrt(np.mean(e ** 2)))
        out["flight_max"] = float(e.max())
    for name, P in PROBES.items():
        uv = []
        for c in cams:
            u, v = c.project(P)
            uv.append(np.array([u[0], v[0]]) + rng.normal(0, noise_px, 2))
        X, res = calib.triangulate(cams[0].intr, exts[0], uv[0], cams[1].intr, exts[1], uv[1])
        out[name] = float(np.linalg.norm(X - P))
    return out


def one(args):
    seed, opt, mount_sigma_in, mount_sigma_deg = args
    rng = np.random.default_rng(1000 + seed)
    cams = [true_cam(opt, "A", rng, "cam0"), true_cam(opt, "B", rng, "cam1")]
    kit_model = tagkit.tag_defs()
    hive = tagkit.hive_tag_defs()
    up = {i: v for i, v in hive.items() if 34 <= i <= 37}
    kit_true = {}
    for i, c in kit_model.items():
        cen = c.mean(0)
        dz = np.radians(rng.normal(0, mount_sigma_deg)) if mount_sigma_deg else 0.0
        Rz = np.array([[math.cos(dz), -math.sin(dz), 0], [math.sin(dz), math.cos(dz), 0], [0, 0, 1]])
        off = rng.normal(0, mount_sigma_in, 3) if mount_sigma_in else np.zeros(3)
        kit_true[i] = (c - cen) @ Rz.T + cen + off
    world = {**kit_true, **up}
    res = {"seed": seed}
    dets = []
    for k, cam in enumerate(cams):
        im = render(cam, world, seed * 7 + k)
        dets.append(calib.detect_apriltags(im))
    res["detected"] = [sorted(d["id"] for d in dets[k]) for k in range(2)]
    variants = {"kit": kit_model, "kit+hive": {**kit_model, **up}, "hive": up}
    for vn, defs in variants.items():
        exts, info, ok = [], [], True
        for k, cam in enumerate(cams):
            try:
                e, used, rp, mx = solve_noisy(cam.intr, dets[k], defs, f"cam{k}", rng, 0.5)
                exts.append(e)
                pe, ae = pose_err(e, cam.extr)
                info.append({"used": used, "reproj_px": rp, "max_px": mx, "pos_err_in": pe, "rot_err_deg": ae})
            except ValueError as ex:
                ok = False
                info.append({"fail": str(ex)})
                exts.append(None)
        r = {"cams": info}
        if ok:
            r["tri"] = triang_errors(cams, exts, rng, 0.5)
        res[vn] = r

    def click_variant(names_xyz, label):
        exts, info, ok = [], [], True
        for k, cam in enumerate(cams):
            pts = np.array([p for _, p in names_xyz])
            u, v = cam.project(pts)
            inim = (u > 0) & (u < W) & (v > 0) & (v < H)
            uv = np.c_[u, v] + rng.normal(0, 1.5, (len(pts), 2))
            try:
                e = calib.solve_extrinsics_from_points(cam.intr, uv, pts, f"cam{k}")
                rep = calib.reprojection_report(cam.intr, e, uv, pts)
                pe, ae = pose_err(e, cam.extr)
                info.append({"reproj_rmse_px": rep["rmse_px"], "max_px": rep["max_px"], "n_in_image": int(inim.sum()),
                             "pos_err_in": pe, "rot_err_deg": ae})
                exts.append(e)
            except Exception as ex:
                ok = False
                info.append({"fail": str(ex)})
                exts.append(None)
        r = {"cams": info}
        if ok:
            r["tri"] = triang_errors(cams, exts, rng, 1.5)
        res[label] = r

    click_variant(ct.field_reference_points(), "click8")
    cell4 = ct.field_reference_points()[:4]
    click_variant(cell4, "click_cell4")
    blue_far = field.cell_opening_polygon("blue", "far", field.HiveState("blue", "far"))
    extra = [(f"bf{i}", p) for i, p in enumerate(blue_far[[3, 2, 1, 0]])]
    click_variant(cell4 + extra, "click_cell_red+bluefar")
    return res


def summarize(rs, label):
    def stat(vals):
        vals = [v for v in vals if v is not None]
        if not vals:
            return "n/a"
        a = np.array(vals)
        return f"median {np.median(a):.2f} p90 {np.percentile(a, 90):.2f} max {a.max():.2f} (n={len(a)})"
    lines = [f"### {label}  (seeds={len(rs)})"]
    for vn in ("kit", "kit+hive", "hive", "click8", "click_cell4", "click_cell_red+bluefar"):
        nfail = sum(1 for r in rs if "tri" not in r[vn])
        lines.append(f"- {vn}: unsolved runs {nfail}/{len(rs)}")
        for k in (0, 1):
            ok = [r[vn]["cams"][k] for r in rs if "fail" not in r[vn]["cams"][k]]
            rp = [c.get("reproj_px", c.get("reproj_rmse_px")) for c in ok]
            extra = f"; tags used median {np.median([len(c['used']) for c in ok]):.0f}" if ok and "used" in ok[0] else ""
            lines.append(f"    cam{k}: solved {len(ok)}/{len(rs)}; reproj px {stat(rp)}; pose pos err in "
                         f"{stat([c['pos_err_in'] for c in ok])}; rot deg {stat([c['rot_err_deg'] for c in ok])}{extra}")
        for p in list(PROBES) + ["flight_rms", "flight_max"]:
            v = [r[vn]["tri"][p] for r in rs if "tri" in r[vn] and p in r[vn]["tri"]]
            frac = np.mean([x < 1 for x in v]) if v else float("nan")
            lines.append(f"    triangulation error {p} (in): {stat(v)}; fraction <1 in: {frac:.2f}")
    return "\n".join(lines)


if __name__ == "__main__":
    opt = sys.argv[1] if len(sys.argv) > 1 else "usb"
    cases = {"mount0": (0.0, 0.0), "mount0.25in_1deg": (0.25, 1.0), "mount1in_2deg": (1.0, 2.0)}
    out = {}
    text = []
    t0 = time.time()
    with Pool(12) as pool:
        for cn, (ms, md) in cases.items():
            rs = pool.map(one, [(s, opt, ms, md) for s in range(30)])
            out[cn] = rs
            text.append(summarize(rs, f"{opt} / tag mounting error sigma {ms} in per axis, {md} deg yaw: {cn}"))
            print(text[-1], flush=True)
            print("elapsed", time.time() - t0, flush=True)
    json.dump(out, open(f"evidence/refute/dod9_2/sim_{opt}.json", "w"), default=float)
    open(f"evidence/refute/dod9_2/sim_{opt}.txt", "w").write("\n\n".join(text))

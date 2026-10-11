r"""Pose error of the printed-kit solve when the tags are NOT taped exactly where the model says.

For each camera at the recommended pose (usb and gopro options): each of the 4 kit tags is displaced
by a vector of fixed magnitude (random direction) and rotated by a fixed angle about a random axis
through its center; the synthetic frame is rendered from the PERTURBED tags (noise 2 gray levels, 3x3
blur), detected with calib.detect_apriltags, and solved with the NOMINAL tag corners
(calib.solve_extrinsics_from_tags). Reported: camera position error (in), rotation error (deg),
reprojection RMSE the app would show (px), and the error of the triangulated up-CELL opening center
(in) from the two solved cameras.
Run: PYTHONPATH=. .venv\Scripts\python.exe -I evidence\refute\dod9_kit_mounting_sim.py [seeds]
"""
import json
import sys

import cv2
import numpy as np

sys.path.insert(0, "tests")
import test_tagkit as T  # noqa: E402

from hiveshot import calib, field, tagkit  # noqa: E402

CASES = [(0.0, 0.0), (0.25, 0.5), (0.5, 1.0), (1.0, 2.0)]


def perturb(corners, mag, ang_deg, rng):
    c = corners.mean(axis=0)
    d = rng.normal(size=3)
    d *= mag / np.linalg.norm(d)
    ax = rng.normal(size=3)
    ax /= np.linalg.norm(ax)
    R = cv2.Rodrigues(ax * np.radians(ang_deg))[0]
    return (corners - c) @ R.T + c + d


def run(option, seeds):
    cams = {k: T._vcam(option, k) for k in "AB"}
    defs = tagkit.tag_defs()
    truth, _ = field.cell_opening_plane("red", "audience", field.HiveState("red", "audience"))
    out = {}
    for mag, ang in CASES:
        rows = []
        for sd in range(seeds):
            rng = np.random.default_rng(1000 + sd)
            true_tags = {t: perturb(c, mag, ang, rng) if mag else c for t, c in defs.items()}
            ests, ok, rec = {}, True, {}
            for k, cam in cams.items():
                img = T.render_tag_dict(cam, true_tags, seed=sd)
                try:
                    e, info = calib.solve_extrinsics_from_tags(cam.intr, img, defs, cam.cam_id)
                except ValueError:
                    ok = False
                    break
                ests[k] = e
                rec[k] = (float(np.linalg.norm(T._pos(e) - T._pos(cam.extr))), T._rot_deg(e, cam.extr),
                          info["reprojection_px"], len(info["tags_used"]))
            if not ok:
                rows.append(None)
                continue
            ua = np.array([a[0] for a in cams["A"].project(truth)])
            ub = np.array([a[0] for a in cams["B"].project(truth)])
            xyz, _ = calib.triangulate(cams["A"].intr, ests["A"], ua, cams["B"].intr, ests["B"], ub)
            rows.append({"A": rec["A"], "B": rec["B"],
                         "cell_err": float(np.linalg.norm(np.asarray(xyz).reshape(-1)[:3] - truth))})
        good = [r for r in rows if r]
        pos = [r[k][0] for r in good for k in "AB"]
        rot = [r[k][1] for r in good for k in "AB"]
        rp = [r[k][2] for r in good for k in "AB"]
        ce = [r["cell_err"] for r in good]
        out[f"{mag}in_{ang}deg"] = {
            "runs": len(rows), "solved": len(good),
            "pos_in_median": float(np.median(pos)), "pos_in_max": float(np.max(pos)),
            "rot_deg_median": float(np.median(rot)), "rot_deg_max": float(np.max(rot)),
            "reproj_px_median": float(np.median(rp)), "reproj_px_max": float(np.max(rp)),
            "reproj_under_2px": int(sum(1 for r in good if r["A"][2] < 2 and r["B"][2] < 2)),
            "cell_err_in_median": float(np.median(ce)), "cell_err_in_max": float(np.max(ce)),
            "tags_used_min": int(min(r[k][3] for r in good for k in "AB")),
            # both gates of the M1 target at once: reprojection < 2 px in BOTH cameras and the
            # triangulated up-CELL opening center within 1 in of its CAD value
            "both_gates_pass": int(sum(1 for r in good
                                       if r["A"][2] < 2 and r["B"][2] < 2 and r["cell_err"] < 1.0)),
        }
    return out


if __name__ == "__main__":
    seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    res = {opt: run(opt, seeds) for opt in ("usb", "gopro")}
    print(json.dumps(res, indent=1))

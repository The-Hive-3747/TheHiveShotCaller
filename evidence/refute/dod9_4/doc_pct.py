"""Independent check of the picture percentages and roll-line numbers in docs/camera_placement.md section 2.
Run: PYTHONPATH=. python evidence/refute/dod9_4/doc_pct.py"""
import math
import numpy as np
from hiveshot import placement as pl, tagkit, field, calib_targets as ct

W, H = pl.RESOLUTION
for opt in ("gopro", "usb"):
    r = pl.recommend(opt)
    for k in "AB":
        c = r["cameras"][k]
        cam = pl._vcam(c["pos"], c["look_at"], c["hfov_deg"])
        def pct(P):
            u, v = cam.project(np.atleast_2d(P))
            return round(100 * u[0] / W), round(100 * v[0] / H)
        ctr = np.array(field.cell_opening_plane("red", "audience", field.HiveState())[0])
        tg = tagkit.up_cell_tag_corners("red", "audience")
        rows = [pct(np.mean(v, axis=0)) for v in tg.values()]
        kit = {t.id: pct(tagkit.tag_corners_xyz(t).mean(0)) for t in tagkit.KIT_TAGS}
        # roll line through tags 100 and 101 centers
        a = tagkit.tag_corners_xyz(100).mean(0); b = tagkit.tag_corners_xyz(101).mean(0)
        ua, va = cam.project(a); ub, vb = cam.project(b)
        du, dv = ub[0] - ua[0], vb[0] - va[0]
        # slope as the doc words it: angle above horizontal going from the right-hand tag to the left-hand one
        ang = math.degrees(math.atan2(-(dv), -(du))) if du < 0 else math.degrees(math.atan2(dv, du))
        print(opt, k, "cell opening centre %/%:", pct(ctr), "tag row (min/max):", min(rows), max(rows), "kit:", kit,
              "| tags 100->101 du,dv px:", round(du), round(dv), "slope (px up per 100 px going left) %.1f" % (100 * (-dv) / abs(du)) if True else "")
        # minimum aim slack: how far can the aim rotate (yaw/pitch +-d) before 8 points / kit tags leave the frame
        pts8 = np.array([p for _, p in ct.field_reference_points()])
        pos = np.array(c["pos"], float); look = np.array(c["look_at"], float)
        for d in (2, 3, 3.5, 4, 5, 5.5, 6):
            ok = True
            for dy, dp in ((d, 0), (-d, 0), (0, d), (0, -d)):
                la = pl._rotated_aim(pos, look, dy, dp)
                cm = pl._vcam(pos, la, c["hfov_deg"])
                if not pl.refs_in_view(cm):
                    ok = False
                kv = pl.kit_view(cm, pos)
                tv = pl.tag_view(cm, pos)
                if kv["n_ok"] < pl.KIT_MIN_TAGS:
                    ok = False
                if r["tags"][k]["sees"] and not tv["sees"]:
                    ok = False
            print("   aim off by %.1f deg in yaw/pitch (each sign): refs + >=3 kit tags (+CELL tags for reader) still ok: %s" % (d, ok))

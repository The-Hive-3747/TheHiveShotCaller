import math, numpy as np
from hiveshot import placement as pl
for opt in ("usb","gopro"):
    r = pl.recommend(opt); print("==", opt, "tri", round(r["pair_score"]["mean_angle_deg"],1), "both", round(r["pair_score"]["frac_in_both"],3), "kit_both", r["pair_score"]["kit_both"], "both_on_wall", r["pair_score"]["both_on_audience_wall"])
    for k in "ABC":
        if k not in r["cameras"]: continue
        c = r["cameras"][k]; yaw, pitch = pl.aim_angles(c)
        om = pl.operator_measurements(c["pos"])
        print(k, c["pos"], "look", c["look_at"], "yaw %.1f pitch %.1f" % (yaw, pitch), "out_outer %.2f along_outer %.2f" % (om["out_from_outer_face_in"], om["along_from_outer_edge_in"]))
    for k in "AB":
        t = r["tags"][k]; print(" tag", k, round(t["angle_deg"],1), t["sees"], round(t["min_edge_px"],1), "kit ok ids", [i for i,d in t["kit"]["tags"].items() if d["ok"]], "kit angles", {i: round(d["angle_deg"],1) for i,d in t["kit"]["tags"].items()}, "edges", {i: round(d["min_edge_px"],1) for i,d in t["kit"]["tags"].items()})
    print(" robot", {k:{a:round(b,3) for a,b in v.items()} for k,v in r["robot"].items()})
    print(" pixel", {k:{a:round(b,1) for a,b in v.items()} for k,v in pl.pixel_numbers(opt).items()})

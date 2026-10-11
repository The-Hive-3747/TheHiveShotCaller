import math, numpy as np
from hiveshot import placement as p, field, calib_targets as ct, tagkit
for opt in ("usb","gopro"):
    r=p.recommend(opt)
    print("==",opt, "tag_reader",r["tag_reader"], "tri", r["pair_score"].get("mean_tri_deg", r["pair_score"]))
    for k,c in r["cameras"].items():
        y,pi=p.aim_angles(c)
        m=p.operator_measurements(c["pos"])
        print(k,c["pos"],"look",c["look_at"],"yaw %.1f pitch %.1f"%(y,pi),"h",c["height_in"],
              "wall",m["wall"],"out_in %.1f along_in %.1f out_outer %.1f along_outer %.1f"%(m["out_from_wall_in"],m["along_wall_from_corner_in"],m["out_from_outer_face_in"],m["along_from_outer_edge_in"]))
    print("tags",{k:{kk:v[kk] for kk in v if kk in("sees","angle_deg","kit")} for k,v in r["tags"].items()})
    print("pixel",p.pixel_numbers(opt))
    print("pct", )
print(p.pixel_numbers.__doc__)
print("CELL center",field.cell_opening_plane("red","audience",field.HiveState("red","audience")) if hasattr(field,'cell_opening_plane') else None)
print(ct.field_reference_points())

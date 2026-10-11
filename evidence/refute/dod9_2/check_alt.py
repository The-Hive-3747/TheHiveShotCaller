from hiveshot import placement as p
for o in ("gopro","usb"):
    r=p.recommend(o)
    print(o,"robot",{k:{kk:round(vv,3) for kk,vv in v.items()} for k,v in r["robot"].items()})
    a=r["both_tags_alternative"]
    print(" alt", {k:(v["pos"], v["look_at"]) for k,v in a["cameras"].items()}, "tri %.1f"%a["pair_score"]["mean_angle_deg"], "frac_both %.3f"%a["pair_score"]["frac_in_both"],
          "tag angles", {k:round(v["angle_deg"],1) for k,v in a["tags"].items()}, "robot", {k:round(v["free"],3) for k,v in a["robot"].items()})
    print(" main frac_in_both %.3f"%r["pair_score"]["frac_in_both"], "occ %.3f"%r["pair_score"]["occluded_frac"])

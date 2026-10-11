import sys, json
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker")
import numpy as np
from hiveshot import placement, tagkit, calib_targets
for opt in ("usb","gopro"):
    r = placement.recommend(opt)
    print(opt, json.dumps({k:r["cameras"][k] for k in "AB"}, default=float))
    print(r["tag_reader"], r["pair_score"])
    for k in "AB":
        cam = placement._vcam(r["cameras"][k]["pos"], r["cameras"][k]["look_at"], r["hfov_deg"], k)
        print(k, {t: (round(d['angle_deg']), round(d['min_edge_px']), d['ok']) for t,d in placement.kit_view(cam, r["cameras"][k]["pos"])["tags"].items()}, placement.refs_in_view(cam))
print(calib_targets.field_reference_points())
for t in tagkit.KIT_TAGS: print(t.id, tagkit.tag_corners_xyz(t).round(2).tolist())

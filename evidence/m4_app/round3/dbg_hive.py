import sys; sys.path.insert(0,'.'); sys.path.insert(0,'tests')
import numpy as np
from tests.test_setup import _computed_world, render_tag_dict
from hiveshot.calib import detect_apriltags
from hiveshot import tagkit, field
cams, tags = _computed_world()
dets = {}
for cid, cam in cams.items():
    fr = render_tag_dict(cam, tags, seed=3)
    img = fr if hasattr(fr,'shape') else fr
    print(cid, type(fr))
    d = detect_apriltags(fr)
    print(cid, [x['id'] for x in d])
    dets[cid] = d
calib = {c:(cams[c].intr, cams[c].extr) for c in cams}
table = {}
for cell in ("audience","far"):
    comp = tagkit.computed_hive_defs if hasattr(tagkit,'computed_hive_defs') else None
print(tagkit.infer_hive_state(None, dets, calib, alliance="red"))
print(tagkit.up_cells_from_tags(dets, calib))
from hiveshot.pipeline import computed_hive_defs
table = {f"red_{c}": computed_hive_defs("red", c) for c in ("audience","far")}
print({k: sorted(v) for k,v in table.items()})
print(tagkit.infer_hive_state(table, dets, calib))
print(tagkit.infer_hive_state(table, {"cam1": dets["cam1"]}, {"cam1":calib["cam1"]}))

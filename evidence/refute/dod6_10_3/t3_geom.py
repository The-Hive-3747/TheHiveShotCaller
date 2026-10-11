import numpy as np, sys, json
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker")
from hiveshot import tagkit, field, placement
defs = tagkit.tag_defs()
print(type(defs), (list(defs)[:4] if hasattr(defs,'__iter__') else defs))
d = defs if isinstance(defs, dict) else {x['id']: x for x in defs}
print(json.dumps({str(k): (v if not isinstance(v, dict) else {kk: (np.round(vv,2).tolist() if hasattr(vv,'__len__') else vv) for kk,vv in v.items()}) for k,v in list(d.items())[:1]}, default=lambda o: np.round(o,2).tolist())[:800])
for tid in (100,101,102,103):
    c = np.asarray(tagkit.tag_corners_xyz(tid)); n = np.asarray(tagkit.tag_normal_xyz(tid))
    cd = np.asarray(d[tid]['corners_xyz'] if isinstance(d[tid], dict) else d[tid])
    print(tid, 'corners', np.round(c,2).tolist(), 'normal', np.round(n,3).tolist(), 'maxdiff vs tag_defs', float(np.abs(cd-c).max()),
      'tilt from vertical deg', round(float(np.degrees(np.arcsin(abs(n[2])))),1))
panel = field.logo_panel_face("audience")
print('panel', type(panel), np.round(np.asarray(panel),2).tolist() if not isinstance(panel, dict) else panel)

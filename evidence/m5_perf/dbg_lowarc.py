import sys, json, tempfile, time
from pathlib import Path
sys.path.insert(0, ".")
import numpy as np
from hiveshot import pipeline as P, field
from hiveshot.shots import opening_classifier, classify
from hiveshot.field import HiveState
orig = P.build_shot
def bs(tr3, sid, shot_id, fns, ball, cc):
    crosses, inside = fns
    pts = tr3.points
    print("--- track", len(pts), "pts, t0=%.3f" % pts[0].t)
    for p in pts[-5:]:
        c, n, w = field._frame("red", "audience", HiveState("red", "audience"))
        rel = np.array([p.x, p.y, p.z]) - c
        print("  t=%.4f xyz=(%.1f %.1f %.1f) depth=%.2f inside=%s" % (p.t, p.x, p.y, p.z, float(np.dot(rel, n)), inside((p.x, p.y, p.z))))
    r = classify(tr3, crosses, inside, cc)
    print("  ->", r)
    return orig(tr3, sid, shot_id, fns, ball, cc)
P.build_shot = bs
sys.argv = ["x", sys.argv[1]]
exec(open("evidence/m5_perf/run_dir.py").read())

import sys, pickle
sys.path.insert(0, ".")
from hiveshot import pipeline as P
tracks = []
ob = P.build_shot
def bs(tr3, *a, **k):
    tracks.append(tr3); return ob(tr3, *a, **k)
P.build_shot = bs
fx = sys.argv[1]; out = sys.argv[2]; sys.argv = ["x", fx]
exec(open("evidence/m5_perf/rt_run.py").read())
pickle.dump(tracks, open(out, "wb")); print("dumped", len(tracks))

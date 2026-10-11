import sys, time, numpy as np, collections
sys.path.insert(0, ".")
from hiveshot import pipeline as P
t_start = [None]
rows = []
od = P.ScaledDetector.detect
def det(self, small, idx, t, cam):
    a = time.perf_counter(); r = od(self, small, idx, t, cam); b = time.perf_counter()
    if cam == "cam0": rows.append((a, b - a, idx))
    return r
P.ScaledDetector.detect = det
ev = []
of = P.Pipeline._finalize
def fin(self, *a, **k):
    s = time.perf_counter()
    try: return of(self, *a, **k)
    finally: ev.append(("finalize", s, time.perf_counter()))
P.Pipeline._finalize = fin
orc = P.Pipeline._recon_cycle
def rc(self, final=False):
    s = time.perf_counter()
    try: return orc(self, final)
    finally: ev.append(("cycle", s, time.perf_counter()))
P.Pipeline._recon_cycle = rc
sys.argv = ["x", sys.argv[1]]
exec(open("evidence/m5_perf/rt_run.py").read())
t0 = rows[0][0]
b = collections.defaultdict(list)
for a, d, i in rows: b[int((a - t0) / 0.25)].append(d * 1000)
print("bucket(s)  frames  mean_detect_ms  | recon cycle ms in bucket | finalize ms in bucket")
for k in sorted(b):
    lo, hi = t0 + k * 0.25, t0 + (k + 1) * 0.25
    cyc = sum(max(0, min(hi, e) - max(lo, s)) for n, s, e in ev if n == "cycle") * 1000
    fin_ = sum(max(0, min(hi, e) - max(lo, s)) for n, s, e in ev if n == "finalize") * 1000
    print("%5.2f  %4d  %6.2f | %6.1f | %6.1f" % (k * 0.25, len(b[k]), np.mean(b[k]), cyc, fin_))

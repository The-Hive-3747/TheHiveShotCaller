import sys, time, numpy as np
sys.path.insert(0, ".")
from hiveshot import pipeline as P
var = sys.argv[2]
durs = {}
od = P.ScaledDetector.detect
def det(self, small, idx, t, cam):
    a = time.perf_counter(); r = od(self, small, idx, t, cam); durs.setdefault(cam, []).append((time.perf_counter() - a) * 1000); return r
P.ScaledDetector.detect = det
if "norecon" in var: P.Pipeline._recon_cycle = lambda self, final=False: None
if "nodrag" in var:
    from hiveshot import physics as _ph
    def _fd(track): raise ValueError("disabled")
    _ph.fit_drag = _fd
if "notags" in var: P.Pipeline._tag_tick = lambda self: None
fx = sys.argv[1]
sys.argv = ["x", fx, "--noclips"] if "noclips" in var else ["x", fx]
exec(open("evidence/m5_perf/rt_run.py").read())
for c, d in durs.items():
    d = np.array(d); print(c, "detect ms: mean %.2f p50 %.2f p90 %.2f p99 %.2f max %.1f  n>4.17: %d" % (d.mean(), np.percentile(d, 50), np.percentile(d, 90), np.percentile(d, 99), d.max(), (d > 4.17).sum()))

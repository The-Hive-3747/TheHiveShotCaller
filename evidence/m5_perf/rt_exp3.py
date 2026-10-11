import sys, time, collections
sys.path.insert(0, ".")
from hiveshot import pipeline as P, recon as R, shots as S, physics as PH
tot = collections.defaultdict(float); cnt = collections.Counter()
def wrap(obj, name, label=None):
    f = getattr(obj, name); label = label or f"{getattr(obj,'__name__',type(obj).__name__)}.{name}"
    def w(*a, **k):
        t = time.perf_counter()
        try: return f(*a, **k)
        finally: tot[label] += time.perf_counter() - t; cnt[label] += 1
    setattr(obj, name, w)
for n in ("_recon_cycle", "_choose_offset", "_ingest_fragment", "_release_chains", "_finalize", "_write_clips", "_extend_into_opening", "_tag_tick", "_link_tips"):
    wrap(P.Pipeline, n)
for n in ("match_tracks", "reconstruct", "choose_offset_by_epipolar", "refine_time_offset"):
    wrap(R.StereoReconstructor, n)
for n in ("build_shot","assign_bursts","classify_track","opening_classifier","summarize"):
    wrap(P, n, "P."+n)
wrap(PH, "fit_drag"); wrap(PH,"fit_parabola")
from hiveshot.store import Store as ST
for n in ("add_shot","list_shots","get_shot","session_summary","update_burst","set_clip_path","list_tips"):
    wrap(ST, n, "Store."+n)
wrap(P.Pipeline,"stats","Pipeline.stats"); wrap(P.Pipeline,"_emit","Pipeline._emit")
import os
var = os.environ.get("VAR", "")
if "nodrag" in var:
    def _fd(track): raise ValueError("disabled")
    PH.fit_drag = _fd
fx = sys.argv[1]; sys.argv = ["x", fx] + (["--noclips"] if "noclips" in var else [])
exec(open("evidence/m5_perf/rt_run.py").read())
for k in sorted(tot, key=lambda k: -tot[k]): print("%-45s calls %4d total %.3f s mean %.1f ms" % (k, cnt[k], tot[k], tot[k]/cnt[k]*1000))

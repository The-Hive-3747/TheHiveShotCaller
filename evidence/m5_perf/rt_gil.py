"""GIL-latency watchdog: which recon phase delays other threads? usage: rt_gil.py fixture"""
import sys, time, threading, collections
sys.path.insert(0, ".")
from hiveshot import pipeline as P, recon as R, physics as PH
from hiveshot.store import Store as ST
phase = {"v": "-"}
tot = collections.defaultdict(float)
def wrap(obj, name, label):
    f = getattr(obj, name)
    def w(*a, **k):
        prev = phase["v"]; phase["v"] = label
        try: return f(*a, **k)
        finally: phase["v"] = prev
    setattr(obj, name, w)
for n in ("_choose_offset", "_ingest_fragment", "_release_chains", "_write_clips", "_extend_into_opening", "_link_tips", "stats", "_emit", "_check_idle"):
    wrap(P.Pipeline, n, n)
for n in ("match_tracks", "reconstruct", "choose_offset_by_epipolar", "refine_time_offset"):
    wrap(R.StereoReconstructor, n, "recon." + n)
wrap(PH, "fit_drag", "fit_drag"); wrap(PH, "fit_parabola", "fit_parabola")
for n in ("add_shot", "list_shots", "get_shot", "update_burst", "set_clip_path"):
    wrap(ST, n, "store." + n)
wrap(P.Pipeline, "_tag_tick", "_tag_tick")
ev = []
stop = [False]
def watch():
    while not stop[0]:
        a = time.perf_counter(); time.sleep(0.001); lat = time.perf_counter() - a - 0.001
        if lat > 0.003: ev.append((a, lat, phase["v"], threading.active_count()))
th = threading.Thread(target=watch, daemon=True); th.start()
fx = sys.argv[1]; sys.argv = ["x", fx]
exec(open("evidence/m5_perf/rt_run.py").read())
stop[0] = True
by = collections.defaultdict(list)
for a, lat, ph, _ in ev: by[ph].append(lat)
print("GIL/timer stalls >3ms by recon phase (count, total ms, max ms):")
for ph, v in sorted(by.items(), key=lambda kv: -sum(kv[1])): print("  %-28s %4d %8.1f %6.1f" % (ph, len(v), sum(v)*1000, max(v)*1000))

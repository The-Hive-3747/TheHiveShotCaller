import sys, time, collections, threading
sys.path.insert(0, ".")
sys.path.insert(0, "evidence/m5_perf")
import thread_cpu
best = {}
stop_flag = [False]
def poll():
    while not stop_flag[0]:
        for tid, (cpu, name) in thread_cpu.snapshot().items():
            if tid not in best or cpu >= best[tid][0]:
                nm = name if name != "native" else best.get(tid, (0, "native"))[1]
                best[tid] = (cpu, nm)
        time.sleep(1.0)
threading.Thread(target=poll, daemon=True, name="poller").start()
import os
if "noclips" in os.environ.get("VAR",""): sys.argv.append("--noclips")
exec(open("evidence/m5_perf/rt_run.py").read())
stop_flag[0] = True
tot = collections.Counter(); nthreads = collections.Counter()
for tid, (cpu, name) in best.items():
    tot[name if name != "native" else "native(opencv/ffmpeg)"] += cpu; nthreads[name] += 1
print("CPU seconds by thread name (sum, #threads):")
for n, c in tot.most_common(14): print("  %-26s %6.2f  (%d)" % (n, c, nthreads[n if n != "native(opencv/ffmpeg)" else "native"]))

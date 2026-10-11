import subprocess, time, os, sys
py = r"C:\Users\3747h\Documents\HiveShotTracker\.venv\Scripts\python.exe"
out = open("evidence/m5_perf/round2_final_cool.txt", "w", encoding="utf-8")
def run(label, cmd, env=None):
    time.sleep(40)
    r = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, **(env or {})})
    keep = [l for l in (r.stdout + r.stderr).splitlines() if l.startswith(("wall", "timing", "shots", "realtime", ".", "PASSED", "FAILED", "1 passed", "1 failed")) or "passed" in l or "failed" in l]
    out.write(f"## {label}\n" + "\n".join(keep) + "\n"); out.flush()
run("pytest HIVESHOT_PERF=1 test_realtime_no_drops", [py, "-m", "pytest", "tests/test_perf.py", "-k", "realtime", "-s", "-o", "addopts="], {"HIVESHOT_PERF": "1"})
run("synth_240", [py, "evidence/m5_perf/rt_run.py", "synth_240"])
run("synth_240 +preview clients", [py, "evidence/m5_perf/rt_run.py", "synth_240", "--preview"])
run("synth_basic", [py, "evidence/m5_perf/rt_run.py", "synth_basic"])
run("synth_20 +preview clients", [py, "evidence/m5_perf/rt_run.py", "synth_20", "--preview"])
open("evidence/m5_perf/final_cool.done", "w").write("ok")

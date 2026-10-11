"""Cool-start realtime runs: for each fixture, REPS runs separated by REST seconds idle.
usage: python cool_runs.py <tree_dir> <label> <out_file> fixture[:flags] ..."""
import subprocess, sys, time, re
tree, label, out = sys.argv[1], sys.argv[2], sys.argv[3]
fixtures = sys.argv[4:]
REPS, REST = 3, 40
py = r"C:\Users\3747h\Documents\HiveShotTracker\.venv\Scripts\python.exe"
with open(out, "a", encoding="utf-8") as f:
    f.write(f"# {label} tree={tree} {time.ctime()} reps={REPS} rest={REST}s\n")
    for fx in fixtures:
        name, *flags = fx.split(":")
        for rep in range(REPS):
            time.sleep(REST)
            r = subprocess.run([py, "evidence/m5_perf/rt_run.py", name] + [f"--{x}" for x in flags], cwd=tree,
                               capture_output=True, text=True)
            lines = [l for l in r.stdout.splitlines() if l.startswith(("wall", "timing(final)", "shots"))]
            f.write(f"## {label} {fx} rep {rep + 1}\n" + "\n".join(lines) + "\n")
            f.flush()

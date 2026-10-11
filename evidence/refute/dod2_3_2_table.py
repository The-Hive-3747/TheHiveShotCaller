import json, sys, glob
from pathlib import Path
d = Path(sys.argv[1])
print("| run | rec/truth | made app/truth | rate app/truth | agree | hist exact | speed max% | >5/>10% | eq missing | dropped c0/c1 | warnings | CPU mean/max |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|")
for f in sorted(d.glob("*.json")):
    r = json.loads(f.read_text())
    if "cmp" not in r: continue
    c = r["cmp"]; fs = r["final_status"]; sl = r["stress_log"]; cp = r.get("cpu_pct", [])
    dr = "/".join(str(max(fs["cameras"][k]["dropped"], sl["max_dropped"].get(k, 0))) for k in ("cam0", "cam1"))
    w = [x for x in sl["warnings_seen"] if "no frames received yet" not in x]
    wtxt = "; ".join(x[:44] for x in w) or "-"
    sp = c["speed_max_abs_pct"]
    print(f"| {f.stem} | {c['n_recorded']}/{c['n_truth']} | {c['app_made']}/{c['truth_made']} | {c['app_rate']:.3f}/{c['truth_rate']:.3f} | {c['makemiss_agree']}/{c['n_truth']} ({c['makemiss_agree_pct']:.0f}%) | {'yes' if c['hist_exact'] else 'NO'} | {'-' if sp is None else f'{sp:.2f}'} | {c['speed_n_over_5']}/{c['speed_n_over_10']} | {c['no_equation']} | {dr} | {wtxt} | {sum(cp)/max(1,len(cp)):.0f}/{max(cp or [0]):.0f} |")

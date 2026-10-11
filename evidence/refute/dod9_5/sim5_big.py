"""More seeds (30..229, disjoint from sim5.py's 0..29) for the documented tolerance case only, to get the tail of the opening-center error.
Run: PYTHONPATH=. .venv/Scripts/python.exe evidence/refute/dod9_5/sim5_big.py usb|gopro"""
import sys, json
src = open("evidence/refute/dod9_5/sim5.py").read().split('if __name__')[0]
exec(src)
opt = sys.argv[1]
rs = [one(s, opt, 0.25, 0.5, 0) for s in range(30, 230)]
t = tally(rs, f"{opt} / mount_0.25 / seeds 30..229")
print(t)
oc = [r["app"]["tri"]["opening_center"] for r in rs if r["app"]["solved"]]
print("app opening center err: p95 %.2f p99 %.2f max %.2f; n>=1in: %d" % (np.percentile(oc, 95), np.percentile(oc, 99), max(oc), sum(o >= 1 for o in oc)))
open(f"evidence/refute/dod9_5/sim5_big_{opt}.txt", "w").write(t)
json.dump(rs, open(f"evidence/refute/dod9_5/sim5_big_{opt}.json", "w"), default=float)

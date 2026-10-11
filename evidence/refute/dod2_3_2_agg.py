import json, glob, os
os.chdir(r"C:\Users\3747h\Documents\HiveShotTracker\evidence\refute\dod2_3_2")
def load(pat):
    out = []
    for f in sorted(glob.glob(pat)):
        r = json.load(open(f))
        if 'cmp' in r: out.append((f, r))
    return out
sets = {"P2 all non-saturated runs": load('p2/*.json')}
for name, runs in sets.items():
    for label, pred in [("excluding lowarc", lambda f: 'lowarc' not in f), ("lowarc only", lambda f: 'lowarc' in f)]:
        s = [(f, r) for f, r in runs if pred(f)]
        tr = sum(r['cmp']['n_truth'] for f, r in s); ag = sum(r['cmp']['makemiss_agree'] for f, r in s)
        rec = sum(r['cmp']['n_recorded'] for f, r in s)
        print(f"{name} {label}: runs={len(s)} shots truth={tr} recorded={rec} make/miss agree={ag} ({100*ag/tr:.1f}%)")
    # speed by fps
    for fps_label, pred in [("60 fps", lambda f: '240' not in f), ("240 fps", lambda f: '240' in f)]:
        errs = []
        for f, r in runs:
            if not pred(f): continue
            errs += [abs(x['speed_err_pct']) for x in r['rows'] if x.get('speed_err_pct') is not None]
        errs.sort()
        print(f"  speed |err| {fps_label}: n={len(errs)} max={errs[-1]:.2f}% median={errs[len(errs)//2]:.3f}% >5%={sum(e>5 for e in errs)} >10%={sum(e>10 for e in errs)}")
    ang = [abs(x['angle_err']) for f, r in runs for x in r['rows'] if x.get('angle_err') is not None]
    print(f"  launch-angle |err| max={max(ang):.2f} deg n={len(ang)}")

import json, glob, os
os.chdir(r"C:\Users\3747h\Documents\HiveShotTracker\evidence\refute\dod2_3_2")
rows = []
for f in sorted(glob.glob('*.json') + glob.glob('p2/*.json') + glob.glob('p2load/*.json')):
    r = json.load(open(f)); f = f.replace(chr(92), '/')
    if 'cmp' not in r: continue
    c = r['cmp']
    w = [x for x in r['stress_log']['warnings_seen'] + r['final_status']['warnings'] if 'no frames received yet' not in x]
    ok = c['n_recorded'] == c['n_truth'] and c['makemiss_agree'] == c['n_truth'] and c['hist_exact'] and (c['speed_max_abs_pct'] or 0) < 5
    rows.append((f, r['mode'], r['stress'], c['n_recorded'], c['n_truth'], c['makemiss_agree'], ok, bool(w), c['speed_max_abs_pct']))


def tally(sel, name):
    s = [x for x in rows if sel(x)]
    print(f"{name}: runs={len(s)} fully-correct={sum(x[6] for x in s)}; incorrect:",
          [(x[0], f'rec {x[3]}/{x[4]}', f'agree {x[5]}/{x[4]}', 'flagged' if x[7] else 'SILENT') for x in s if not x[6]])


nl = lambda x: 'load' not in x[0]
tally(lambda x: x[0].startswith('p2/') and x[1] == 'lockstep', 'A. Phase-2 snapshot, lockstep')
tally(lambda x: x[0].startswith('p2/') and x[1] == 'rt' and not x[2], 'B. Phase-2 snapshot, realtime, no preview/stats clients')
tally(lambda x: x[0].startswith('p2/') and x[2], 'C. Phase-2 snapshot, realtime + 2 MJPEG + stats polling')
tally(lambda x: not x[0].startswith('p2') and nl(x) and x[1] == 'lockstep', 'D. working tree (earlier), lockstep')
tally(lambda x: not x[0].startswith('p2') and nl(x) and x[1] == 'rt' and not x[2], 'E. working tree, realtime')
tally(lambda x: not x[0].startswith('p2') and nl(x) and x[2], 'F. working tree, realtime + stress')
tally(lambda x: 'load' in x[0] and not any(k in x[0] for k in ('x_load4', 'x_load8', 'x_load14')), 'G. CPU saturation (12 busy loops)')

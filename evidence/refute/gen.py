"""Adversarial fixture generator using hiveshot.synth API. usage: gen.py <scenario> <outdir>"""
import json, math, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker")
from hiveshot import synth, field
from hiveshot.field_constants import GRAVITY_IPS2, POLLEN_DIAMETER

sc, out = sys.argv[1], sys.argv[2]
fps = float(sys.argv[3]) if len(sys.argv) > 3 else 60.0
seed = int(sys.argv[4]) if len(sys.argv) > 4 else 4242
cams = synth.make_default_pair()

def bursts(spec, spacing, gap, t0=0.0):
    offs = synth._parse_bursts(spec, spacing, gap)
    return [t0 + o for o in offs]

def save(trajs, info):
    synth.render_sequence(trajs, cams, fps, out, tail_s=float(__import__("os").environ.get("TAIL","0.2")))
    Path(out, "shots.json").write_text(json.dumps(info, indent=1))
    print(sc, "made", sum(s["made"] for s in info), "/", len(info), [round(s["t_launch"],3) for s in info])

if sc == "late20":      # 20 shots, 0.25 spacing, but starting at t=1.0 (not frame 0)
    tr, info = synth.build_shots(bursts("4,4,4,4,4", 0.25, 3.0, 1.0), seed); save(tr, info)
elif sc == "overlap":   # 0.15 s apart
    tr, info = synth.build_shots(bursts("4,4", 0.15, 3.0, 1.0), seed); save(tr, info)
elif sc == "burst6":
    tr, info = synth.build_shots(bursts("6,3", 0.25, 3.0, 1.0), seed); save(tr, info)
elif sc == "gap15":     # two bursts separated by exactly 1.5 s (last launch -> first launch)
    tr, info = synth.build_shots(bursts("3,3", 0.3, 1.5, 1.0), seed); save(tr, info)
elif sc == "spacing_20_30":   # spec-conforming 20-shot, 0.3 spacing, offset 1.0
    tr, info = synth.build_shots(bursts("4,4,4,4,4", 0.3, 3.0, 1.0), seed); save(tr, info)
elif sc in ("lowarc", "edge"):
    # custom: shots from a launch point aimed with the flattest solution (lowarc) or at opening edge
    rng = np.random.default_rng(seed)
    st = field.HiveState("red", "audience")
    center, _ = field.cell_opening_plane("red", "audience", st)
    radius = POLLEN_DIAMETER / 2
    h = 72.0
    offs = bursts("3,3", 0.4, 3.0, 1.0)
    trajs, info = [], []
    i = 0
    tries = 0
    while len(trajs) < len(offs) and tries < 5000:
        tries += 1
        lp = np.array([rng.uniform(-50, 50), rng.uniform(25, 60), 12.0])
        d = np.linalg.norm(lp - center)
        if not 70 <= d <= 110: continue
        speed = float(rng.uniform(260, 600)) if sc == "lowarc" else float(rng.uniform(220, 245))
        try:
            v0 = synth.aim_for_cell(lp, "red", "audience", st, speed, arc="low" if sc == "lowarc" else "high")
        except ValueError:
            continue
        el = math.degrees(math.atan2(v0[2], math.hypot(v0[0], v0[1])))
        if sc == "lowarc" and not 20 <= el <= 50: continue
        if sc == "edge" and not 66.0 <= lp[2] + v0[2]**2/(2*GRAVITY_IPS2) <= 84.0: continue
        if sc == "edge":
            # rotate azimuth so ball lands near lateral edge of opening (+-7 in half width ~ 10 in): offset ~ +-8 in
            rng_h = math.hypot(*(center[:2]-lp[:2]))
            a_ = math.atan2(rng.choice([-1,1]) * 5.0, rng_h)
            c, s_ = math.cos(a_), math.sin(a_)
            v0 = np.array([c*v0[0]-s_*v0[1], s_*v0[0]+c*v0[1], v0[2]])
        tr = synth.simulate_trajectory(lp, v0, 1/1000, 3.0)
        end = len(tr)
        outside = np.nonzero((np.abs(tr[:,1])>h)|(np.abs(tr[:,2])>h))[0]
        if len(outside): end = int(outside[0])
        made = False
        for k in range(end-1):
            if field.segment_crosses_opening(tr[k,1:], tr[k+1,1:], "red", "audience", st, radius):
                made = True; end = k+2; break
        tr = tr[:end]
        if not synth._flight_visible(tr, cams): continue
        t0 = offs[len(trajs)]
        trajs.append((float(t0), tr))
        info.append({"shot": len(info), "t_launch": float(t0), "launch_point": lp.tolist(), "speed_ips": speed,
                     "v0": v0.tolist(), "made": bool(made), "apex_z_in": float(tr[:,3].max()),
                     "duration_s": float(tr[-1,0]), "elev_deg": el})
    print("tries", tries, "elev", [round(s["elev_deg"],1) for s in info], "apex", [round(s["apex_z_in"]) for s in info])
    save(trajs, info)

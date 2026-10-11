p="evidence/refute/dod9_2/sim.py"
s=open(p).read()
s=s.replace('''def triang_errors(cams, exts, rng, noise_px):
    out = {}''','''_TRAJ = None


def traj_points():
    global _TRAJ
    if _TRAJ is None:
        _TRAJ = pl._stack(pl.sample_trajectories())[::4]
    return _TRAJ


def triang_errors(cams, exts, rng, noise_px):
    out = {}
    pts = traj_points()
    m = np.ones(len(pts), bool)
    uvs = []
    for c in cams:
        u, v = c.project(pts)
        m &= (u > 20) & (u < W - 20) & (v > 20) & (v < H - 20) & (c.depth(pts) > 0)
        uvs.append(np.c_[u, v])
    if m.sum() >= 5:
        ua = uvs[0][m] + rng.normal(0, noise_px, (m.sum(), 2))
        ub = uvs[1][m] + rng.normal(0, noise_px, (m.sum(), 2))
        X, _ = calib.triangulate(cams[0].intr, exts[0], ua, cams[1].intr, exts[1], ub)
        e = np.linalg.norm(X - pts[m], axis=1)
        out["flight_rms"] = float(np.sqrt(np.mean(e ** 2)))
        out["flight_max"] = float(e.max())''')
s=s.replace('for p in PROBES:\n            v = [r[vn]["tri"][p] for r in rs if "tri" in r[vn]]','for p in list(PROBES) + ["flight_rms", "flight_max"]:\n            v = [r[vn]["tri"][p] for r in rs if "tri" in r[vn] and p in r[vn]["tri"]]')
open(p,"w").write(s)

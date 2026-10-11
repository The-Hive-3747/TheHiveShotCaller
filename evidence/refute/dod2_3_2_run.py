"""Round-2 refuter harness: drive the REAL app (python -m hiveshot[.app]) over HTTP on a fixture dir.
usage: dod2_3_2_run.py <fixture_dir> <port> <mode: lockstep|rt|rtcli> <out_json> [--stress] [--gap 1.5]
 lockstep: config file with realtime=False for both file sources
 rt:       config file with realtime=True
 rtcli:    `python -m hiveshot.app --source cam0=.. --source cam1=..` (CLI forces realtime=True)
--stress: 2 MJPEG preview clients + /stats polled ~10 Hz during the run; status warnings/dropped recorded.
Compares against <fixture>/shots.json (truth). Kills the server on exit."""
import json, math, subprocess, sys, tempfile, threading, time, urllib.request
from pathlib import Path

import os
REPO = Path(os.environ.get("HS_ROOT", r"C:\Users\3747h\Documents\HiveShotTracker"))   # code under test (cwd of the server)
PY = Path(r"C:\Users\3747h\Documents\HiveShotTracker\.venv\Scripts\python.exe")
fx = Path(sys.argv[1]); port = int(sys.argv[2]); mode = sys.argv[3]; out = Path(sys.argv[4])
stress = "--stress" in sys.argv
gap = float(sys.argv[sys.argv.index("--gap") + 1]) if "--gap" in sys.argv else 1.5
tmp = Path(tempfile.mkdtemp(prefix="r2app_"))
srcs = [{"cam_id": f"cam{i}", "kind": "file", "target": str(fx / f"cam{i}.mp4"), "loop": False,
         "realtime": mode == "rt"} for i in (0, 1)]
cmd = [str(PY)]
if mode == "rtcli":
    cmd += ["-m", "hiveshot.app", "--data-dir", str(tmp), "--port", str(port)]
    for i in (0, 1):
        cmd += ["--source", f"cam{i}={fx / f'cam{i}.mp4'}"]
else:
    (tmp / "config.json").write_text(json.dumps({"sources": srcs}))
    cmd += ["-m", "hiveshot", "--data-dir", str(tmp), "--config", str(tmp / "config.json"), "--port", str(port)]
srv = subprocess.Popen(cmd, cwd=str(REPO), stdout=open(tmp / "srv.out", "w"), stderr=subprocess.STDOUT)
base = f"http://127.0.0.1:{port}"


def get(path, raw=False, timeout=30):
    with urllib.request.urlopen(base + path, timeout=timeout) as r:
        b = r.read()
        return b.decode() if raw else json.loads(b)


def post(path, body=None):
    req = urllib.request.Request(base + path, data=json.dumps(body or {}).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


import ctypes
from ctypes import wintypes
class _FT(ctypes.Structure): _fields_ = [("lo", wintypes.DWORD), ("hi", wintypes.DWORD)]
def _times():
    i, k, u = _FT(), _FT(), _FT()
    ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(i), ctypes.byref(k), ctypes.byref(u))
    f = lambda x: (x.hi << 32) | x.lo
    return f(i), f(k), f(u)
def cpu_sampler(log, stop_ev):
    a = _times()
    while not stop_ev.is_set():
        time.sleep(1.0)
        b = _times()
        di, dk, du = b[0]-a[0], b[1]-a[1], b[2]-a[2]
        tot = dk + du
        log.append(round(100.0 * (tot - di) / tot, 1) if tot else 0.0)
        a = b
stop = threading.Event()
cpu_log = []
threading.Thread(target=cpu_sampler, args=(cpu_log, stop), daemon=True).start()
stress_log = {"mjpg_bytes": [0, 0], "mjpg_err": [], "stats_calls": 0, "stats_err": [], "stats_max_ms": 0.0,
              "status_samples": 0, "max_dropped": {}, "warnings_seen": [], "reader_errors": [], "det_fps": []}


def mjpg(i):
    try:
        with urllib.request.urlopen(f"{base}/api/preview/cam{i}.mjpg", timeout=30) as r:
            while not stop.is_set():
                b = r.read(65536)
                if not b:
                    break
                stress_log["mjpg_bytes"][i] += len(b)
    except Exception as e:  # noqa: BLE001
        stress_log["mjpg_err"].append(f"cam{i}: {e!r}")


def stats_poll(sid):
    while not stop.is_set():
        t = time.perf_counter()
        try:
            get(f"/api/sessions/{sid}/stats", timeout=10)
            stress_log["stats_calls"] += 1
            stress_log["stats_max_ms"] = max(stress_log["stats_max_ms"], (time.perf_counter() - t) * 1000)
        except Exception as e:  # noqa: BLE001
            stress_log["stats_err"].append(repr(e))
        time.sleep(0.1)


res = {"fixture": str(fx), "mode": mode, "stress": stress, "cmd": cmd}
try:
    for _ in range(80):
        try:
            get("/api/config"); break
        except Exception:
            time.sleep(0.5)
    sid = post("/api/sessions", {"name": "r2"})["session_id"]
    threads = []
    t0 = time.time()
    post("/api/pipeline/start")
    if stress:
        time.sleep(0.5)
        for i in (0, 1):
            th = threading.Thread(target=mjpg, args=(i,), daemon=True); th.start(); threads.append(th)
        th = threading.Thread(target=stats_poll, args=(sid,), daemon=True); th.start(); threads.append(th)
    last_n = -1; stable = 0; ended_at = None
    while time.time() - t0 < 300:
        st = get("/api/pipeline/status")
        stress_log["status_samples"] += 1
        for c, d in st["cameras"].items():
            stress_log["max_dropped"][c] = max(stress_log["max_dropped"].get(c, 0), d.get("dropped", 0))
            if d.get("last_error"): stress_log["reader_errors"].append(f"{c}: {d['last_error']}")
        for w in st.get("warnings", []):
            if w not in stress_log["warnings_seen"]: stress_log["warnings_seen"].append(w)
        stress_log["det_fps"].append(round(st.get("detector_fps", 0), 1))
        done = all(not c.get("is_alive") for c in st["cameras"].values()) and \
            min(c["frames_read"] for c in st["cameras"].values()) > 100
        if done:
            ended_at = ended_at or time.time()
            n = len(get(f"/api/sessions/{sid}/shots"))
            stable = stable + 1 if n == last_n else 0
            last_n = n
            if stable >= 3 and time.time() - ended_at > 5:
                break
        time.sleep(1)
    res["elapsed_s"] = time.time() - t0
    res["video_len_s"] = None
    stop.set()
    time.sleep(0.5)
    stats = get(f"/api/sessions/{sid}/stats")
    shots = get(f"/api/sessions/{sid}/shots")
    status = get("/api/pipeline/status")
    csvt = get(f"/api/sessions/{sid}/export.csv", raw=True)
    res.update(stats=stats, shots=shots, final_status={k: status[k] for k in ("warnings", "cameras", "timing", "detector_fps")},
               csv_rows=len(csvt.strip().splitlines()) - 1, stress_log=stress_log, cpu_pct=cpu_log)
finally:
    stop.set()
    srv.terminate()
    try:
        srv.wait(15)
    except Exception:
        srv.kill()
    res["server_exit"] = srv.poll()

# ---- compare with truth
truth = sorted(json.loads((fx / "shots.json").read_text()), key=lambda t: t["t_launch"])
shots = sorted(res["shots"], key=lambda s: s["t_launch"])


def bursts(ts, g):
    r = []; b = 0; idx = 0; last = None
    for t in ts:
        if last is None or t - last > g: b += 1; idx = 0
        idx += 1; last = t; r.append((b, idx))
    return r


tb = bursts([t["t_launch"] for t in truth], gap)
exp_hist = {str(k): 0 for k in range(1, 6)}
for t, (b, i) in zip(truth, tb):
    if not t["made"]: exp_hist[str(min(i, 5))] += 1
pairs = sorted(((abs(s["t_launch"] - t["t_launch"]), ti, si) for ti, t in enumerate(truth) for si, s in enumerate(shots)
                if abs(s["t_launch"] - t["t_launch"]) <= 0.25))
mt, ms = {}, {}
for d, ti, si in pairs:
    if ti in mt or si in ms: continue
    mt[ti] = si; ms[si] = ti
rows = []
for ti, t in enumerate(truth):
    r = {"truth": t["shot"], "t_launch": t["t_launch"], "made_truth": t["made"], "matched": ti in mt}
    if ti in mt:
        s = shots[mt[ti]]
        el = math.degrees(math.atan2(t["v0"][2], math.hypot(t["v0"][0], t["v0"][1])))
        r.update(dt=s["t_launch"] - t["t_launch"], result=s["result"],
                 agree=(t["made"] == (s["result"] == "made")),
                 speed_truth=t["speed_ips"], speed=s["exit_speed_ips"],
                 speed_err_pct=None if s["exit_speed_ips"] is None else 100 * (s["exit_speed_ips"] / t["speed_ips"] - 1),
                 angle_truth=el, angle=s["launch_angle_deg"],
                 angle_err=None if s["launch_angle_deg"] is None else s["launch_angle_deg"] - el,
                 equation=bool(s.get("equation")), burst=(s["burst_id"], s["burst_index"]), burst_truth=tb[ti],
                 ball_type=s["ball_type"], ball_type_truth=t.get("ball_type", "pollen"))
    rows.append(r)
n_truth = len(truth); n_agree = sum(1 for r in rows if r.get("agree"))
errs = [abs(r["speed_err_pct"]) for r in rows if r.get("speed_err_pct") is not None]
res["cmp"] = {
    "n_truth": n_truth, "n_recorded": len(shots), "n_matched": len(mt), "extra": len(shots) - len(mt),
    "truth_made": sum(t["made"] for t in truth), "app_made": res["stats"]["made"],
    "truth_rate": sum(t["made"] for t in truth) / n_truth, "app_rate": res["stats"]["make_rate"],
    "makemiss_agree": n_agree, "makemiss_agree_pct": 100.0 * n_agree / n_truth,
    "exp_hist": exp_hist, "app_hist": res["stats"]["failure_order_hist"],
    "hist_exact": {k: int(v) for k, v in res["stats"]["failure_order_hist"].items()} == exp_hist,
    "speed_n": len(errs), "speed_max_abs_pct": max(errs) if errs else None,
    "speed_n_over_5": sum(e > 5 for e in errs), "speed_n_over_10": sum(e > 10 for e in errs),
    "speed_none": sum(1 for r in rows if r["matched"] and r.get("speed") is None),
    "no_equation": sum(1 for r in rows if r["matched"] and not r.get("equation")),
    "angle_max_abs_err_deg": max([abs(r["angle_err"]) for r in rows if r.get("angle_err") is not None] or [None]),
    "unmatched_truth": [r["truth"] for r in rows if not r["matched"]],
    "results": {k: sum(1 for s in shots if s["result"] == k) for k in ("made", "bounce_out", "miss", "unknown")},
    "burst_mismatch": [r["truth"] for r in rows if r["matched"] and tuple(r["burst"]) != tuple(r["burst_truth"])],
    "by_ball_type": res["stats"]["by_ball_type"],
    "ball_type_wrong": [r["truth"] for r in rows if r["matched"] and r["ball_type"] != r["ball_type_truth"]],
    "dt_max_abs": max([abs(r["dt"]) for r in rows if r.get("dt") is not None] or [None]),
}
res["rows"] = rows
out.write_text(json.dumps(res, indent=1, default=str))
c = res["cmp"]
print(f"[{fx.name} {mode}{' stress' if stress else ''}] elapsed={res['elapsed_s']:.1f}s recorded={c['n_recorded']}/{c['n_truth']} matched={c['n_matched']} extra={c['extra']}"
      f" made app/truth={c['app_made']}/{c['truth_made']} rate app/truth={c['app_rate']}/{c['truth_rate']:.3f}")
print(f"  makemiss agree {c['makemiss_agree']}/{n_truth}={c['makemiss_agree_pct']:.1f}% results={c['results']} hist app={c['app_hist']} exp={exp_hist} exact={c['hist_exact']}")
print(f"  speed n={c['speed_n']} max|err|={c['speed_max_abs_pct']} >5%:{c['speed_n_over_5']} >10%:{c['speed_n_over_10']} none:{c['speed_none']} noeq:{c['no_equation']} angle max err={c['angle_max_abs_err_deg']} csv_rows={res['csv_rows']}")
print(f"  unmatched truth={c['unmatched_truth']} burst mismatch={c['burst_mismatch']} ball_type={c['by_ball_type']} wrong={c['ball_type_wrong']}")
fs = res["final_status"]
print(f"  dropped={ {k: v['dropped'] for k, v in fs['cameras'].items()} } max_dropped_seen={stress_log['max_dropped']} warnings_final={fs['warnings']} warnings_seen={stress_log['warnings_seen']} offset={fs['timing'].get('offset_s')}")
if stress:
    print(f"  stress: mjpg_bytes={stress_log['mjpg_bytes']} mjpg_err={stress_log['mjpg_err']} stats_calls={stress_log['stats_calls']} stats_err={len(stress_log['stats_err'])} stats_max_ms={stress_log['stats_max_ms']:.0f}")
cl = res["cpu_pct"]
print(f"  system CPU during run (whole machine, incl. server): mean={sum(cl)/max(1,len(cl)):.0f}% max={max(cl or [0]):.0f}% n={len(cl)}")
print("  server_exit", res["server_exit"])

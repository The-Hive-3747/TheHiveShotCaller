"""Drive the real FastAPI app (python -m hiveshot) over HTTP on a fixture; compare with shots.json."""
import json, subprocess, sys, time, tempfile, urllib.request
from pathlib import Path
fx = Path(sys.argv[1]); port = int(sys.argv[2]); out = Path(sys.argv[3]); rt = sys.argv[4] == "1" if len(sys.argv) > 4 else False
tmp = Path(tempfile.mkdtemp(prefix="refute_app_"))
cfg = {"sources": [{"cam_id": f"cam{i}", "kind": "file", "target": str(fx / f"cam{i}.mp4"), "loop": False, "realtime": rt} for i in (0, 1)]}
(tmp / "config.json").write_text(json.dumps(cfg))
p = subprocess.Popen([r"C:\Users\3747h\Documents\HiveShotTracker\.venv\Scripts\python.exe", "-m", "hiveshot", "--data-dir", str(tmp), "--config", str(tmp / "config.json"), "--port", str(port)],
                     cwd=r"C:\Users\3747h\Documents\HiveShotTracker", stdout=open(tmp / "srv.out", "w"), stderr=subprocess.STDOUT)
base = f"http://127.0.0.1:{port}"
def get(path, raw=False):
    with urllib.request.urlopen(base + path, timeout=30) as r:
        b = r.read(); return b.decode() if raw else json.loads(b)
def post(path, body=None):
    req = urllib.request.Request(base + path, data=json.dumps(body or {}).encode(), method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r: return json.loads(r.read())
try:
    for _ in range(60):
        try: get("/api/config"); break
        except Exception: time.sleep(0.5)
    sid = post("/api/sessions", {"name": "refute20"})["session_id"]
    post("/api/pipeline/start")
    t0 = time.time()
    while time.time() - t0 < 240:
        st = get("/api/pipeline/status")
        if all(not c.get("is_alive") for c in st["cameras"].values()) and st["cameras"]["cam0"]["frames_read"] > 100:
            time.sleep(3); break
        time.sleep(1)
    time.sleep(2)
    stats = get(f"/api/sessions/{sid}/stats"); shots = get(f"/api/sessions/{sid}/shots"); csvt = get(f"/api/sessions/{sid}/export.csv", raw=True)
    detail = get(f"/api/shots/{shots[0]['shot_id']}") if shots else None
    res = {"stats": stats, "shots": shots, "csv_head": csvt.splitlines()[:3], "csv_rows": len(csvt.strip().splitlines()) - 1, "detail_keys": sorted(detail) if detail else None, "elapsed": time.time() - t0}
    out.write_text(json.dumps(res, indent=1))
    truth = sorted(json.load(open(fx / "shots.json")), key=lambda t: t["t_launch"])
    print("truth shots", len(truth), "made", sum(t["made"] for t in truth))
    print("app stats", json.dumps({k: stats[k] for k in ("shots", "made", "bounce_out", "miss", "unknown", "make_rate", "by_ball_type", "failure_order_hist")}))
    print("csv rows", res["csv_rows"], "shots keys", sorted(shots[0]) if shots else None)
    print("with equation:", sum(1 for s in shots if s.get("equation")), "with speed:", sum(1 for s in shots if s.get("exit_speed_ips")), "with angle:", sum(1 for s in shots if s.get("launch_angle_deg") is not None))
    print("sample eq:", shots[0].get("equation") if shots else None)
finally:
    p.terminate()
    try: p.wait(10)
    except Exception: p.kill()
    print("server exit", p.poll())

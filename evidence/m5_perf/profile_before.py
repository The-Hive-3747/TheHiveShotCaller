"""Baseline per-stage CPU timing replicating the pre-optimisation per-frame path.
Single thread, thread CPU time (time.thread_time) AND perf_counter reported."""
import dataclasses, sys, time, json
import cv2, numpy as np
sys.path.insert(0, ".")
from hiveshot.detect import BallDetector, DetectorConfig
from hiveshot.track2d import Tracker2D
from hiveshot import config as cfgmod

cv2.setNumThreads(1)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 240
cap = cv2.VideoCapture("fixtures/synth_basic/cam0.mp4")
det = BallDetector(DetectorConfig.from_dict(cfgmod.AppConfig().detector.model_dump()))
trk = Tracker2D("cam0")
acc = {k: [0.0, 0.0] for k in ("detect", "track", "preview", "ring")}
n = 0
while n < N:
    ok, img = cap.read()
    if not ok:
        break
    t = n / 60.0
    def stage(name, fn):
        c0, w0 = time.thread_time(), time.perf_counter()
        r = fn()
        acc[name][0] += time.thread_time() - c0
        acc[name][1] += time.perf_counter() - w0
        return r
    dets = stage("detect", lambda: det.detect(img, n, t, "cam0"))
    stage("track", lambda: (trk.update(dets, n, t), trk.closed()))
    h, w = img.shape[:2]
    def preview():
        s = min(1.0, 960 / w)
        im = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        sd = [dataclasses.replace(d, u=d.u * s, v=d.v * s, radius_px=d.radius_px * s) for d in dets]
        ok, buf = cv2.imencode(".jpg", det.draw(im, sd), [cv2.IMWRITE_JPEG_QUALITY, 75])
        return buf.tobytes()
    def ring():
        s = min(1.0, 480 / w)
        return cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    # old path: preview encoded at preview_fps (15) -> every 4th frame at 60 fps source
    if n % 4 == 0:
        stage("preview", preview)
    stage("ring", ring)
    n += 1
print(f"frames={n} size={w}x{h}")
tot_c = tot_w = 0
for k, (c, w_) in acc.items():
    print(f"{k:8s} cpu {c/n*1000:7.3f} ms/frame  wall {w_/n*1000:7.3f} ms/frame")
    tot_c += c; tot_w += w_
print(f"{'sum':8s} cpu {tot_c/n*1000:7.3f} ms/frame  wall {tot_w/n*1000:7.3f} ms/frame")

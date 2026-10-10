import sys, time
import cv2, numpy as np
sys.path.insert(0, ".")
from hiveshot.detect import BallDetector, DetectorConfig
from hiveshot import config as cfgmod
cv2.setNumThreads(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
cap = cv2.VideoCapture("fixtures/synth_basic/cam0.mp4")
cfg = DetectorConfig.from_dict(cfgmod.AppConfig().detector.model_dump())
print(cfg)
det = BallDetector(cfg)
parts = {}
def tm(name, fn):
    t0 = time.perf_counter(); r = fn(); parts.setdefault(name, []).append(time.perf_counter() - t0); return r
n = 0
while n < 120:
    ok, img = cap.read()
    if not ok: break
    small = tm("resize_area_0.5", lambda: cv2.resize(img, None, fx=.5, fy=.5, interpolation=cv2.INTER_AREA))
    tm("resize_linear_0.5", lambda: cv2.resize(img, None, fx=.5, fy=.5, interpolation=cv2.INTER_LINEAR))
    tm("resize_area_480", lambda: cv2.resize(img, (480, 270), interpolation=cv2.INTER_AREA))
    tm("resize_small_to_480", lambda: cv2.resize(small, (480, 270), interpolation=cv2.INTER_AREA))
    mo = tm("mog2", lambda: det._bg.apply(small))
    hsv = tm("cvtHSV", lambda: cv2.cvtColor(small, cv2.COLOR_BGR2HSV))
    p = tm("inRange_p", lambda: cv2.inRange(hsv, np.array(cfg.pollen_hsv[0], np.uint8), np.array(cfg.pollen_hsv[1], np.uint8)))
    q = tm("inRange_n", lambda: cv2.inRange(hsv, np.array(cfg.nectar_hsv[0], np.uint8), np.array(cfg.nectar_hsv[1], np.uint8)))
    m = tm("or_and", lambda: cv2.bitwise_and(mo, cv2.bitwise_or(p, q)))
    m = tm("morph", lambda: cv2.morphologyEx(cv2.morphologyEx(m, cv2.MORPH_OPEN, det._kernel), cv2.MORPH_CLOSE, det._kernel))
    tm("contours", lambda: cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE))
    tm("detect_total", lambda: det.detect(img, n, n/60, "c"))
    tm("imencode_960", lambda: cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 75]))
    n += 1
for k, v in parts.items():
    print(f"{k:22s} mean {np.mean(v)*1000:7.3f}  median {np.median(v)*1000:7.3f} ms")

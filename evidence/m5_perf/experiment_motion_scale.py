"""Experiment: run the MOG2 motion model at a lower resolution than the colour masks and
compare detections with the stock detector on the synthetic fixtures (not used by the app)."""
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, ".")
from hiveshot import config as cfgmod  # noqa: E402
from hiveshot.detect import BallDetector, DetectorConfig  # noqa: E402
from hiveshot.pipeline import ScaledDetector  # noqa: E402

cv2.setNumThreads(1)
MS = float(sys.argv[1]) if len(sys.argv) > 1 else 0.5       # motion scale relative to the small frame
fixture = sys.argv[2] if len(sys.argv) > 2 else "synth_basic"
cfg = DetectorConfig.from_dict(cfgmod.AppConfig().detector.model_dump())


class LowMotion(BallDetector):
    def _masks(self, small):
        h, w = small.shape[:2]
        ms = cv2.resize(small, (int(w * MS), int(h * MS)), interpolation=cv2.INTER_AREA)
        motion = cv2.resize(self._bg.apply(ms), (w, h), interpolation=cv2.INTER_NEAREST)
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        c = self.cfg
        pollen = cv2.inRange(hsv, np.array(c.pollen_hsv[0], np.uint8), np.array(c.pollen_hsv[1], np.uint8))
        nectar = cv2.inRange(hsv, np.array(c.nectar_hsv[0], np.uint8), np.array(c.nectar_hsv[1], np.uint8))
        mask = cv2.bitwise_and(motion, cv2.bitwise_or(pollen, nectar))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self._kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self._kernel)
        return mask, pollen, nectar


base = ScaledDetector(cfg)
fast = ScaledDetector(cfg)
fast.det = LowMotion(fast.det.cfg)
tb = tf = 0.0
same = diff = 0
maxd = 0.0
n = 0
for cam in ("cam0", "cam1"):
    cap = cv2.VideoCapture(f"fixtures/{fixture}/{cam}.mp4")
    base = ScaledDetector(cfg)
    fast = ScaledDetector(cfg)
    fast.det = LowMotion(fast.det.cfg)
    i = 0
    while True:
        ok, img = cap.read()
        if not ok:
            break
        sm = base.shrink(img)
        t0 = time.perf_counter()
        a = base.detect(sm, i, i / 60, cam)
        t1 = time.perf_counter()
        b = fast.detect(sm, i, i / 60, cam)
        t2 = time.perf_counter()
        tb += t1 - t0
        tf += t2 - t1
        n += 1
        if len(a) == len(b):
            same += 1
            for x, y in zip(sorted(a, key=lambda d: d.u), sorted(b, key=lambda d: d.u), strict=True):
                maxd = max(maxd, ((x.u - y.u) ** 2 + (x.v - y.v) ** 2) ** 0.5)
        else:
            diff += 1
        i += 1
print(f"{fixture} motion_scale={MS}: stock {tb/n*1000:.2f} ms  low-res-motion {tf/n*1000:.2f} ms  "
      f"frames same-count {same} / differ {diff}  max centre shift {maxd:.2f} px (full-res)")

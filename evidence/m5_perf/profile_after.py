"""Per-stage timing of the optimised per-frame path, using the real Pipeline code
(ScaledDetector, Tracker2D, Pipeline._after_frame). Single thread (cv2.setNumThreads(1)),
perf_counter. Preview JPEG is forced every 4th frame (15 fps preview of a 60 fps source),
clip ring enabled, like profile_before.py. Prints mean and median ms per frame."""
import collections
import sys
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, ".")
from hiveshot import config as cfgmod  # noqa: E402
from hiveshot.detect import DetectorConfig  # noqa: E402
from hiveshot.ingest import Frame  # noqa: E402
from hiveshot.pipeline import Pipeline, ScaledDetector  # noqa: E402
from hiveshot.store import Store  # noqa: E402
from hiveshot.track2d import Tracker2D  # noqa: E402

cv2.setNumThreads(1)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 240
tmp = Path(tempfile.mkdtemp())
pl = Pipeline(cfgmod.AppConfig(), Store(tmp / "p.db"), tmp, save_clips=True)
pl._ring = {"cam0": collections.deque()}
MS = float(sys.argv[2]) if len(sys.argv) > 2 else cfgmod.AppConfig().detector.motion_scale
det = ScaledDetector(DetectorConfig.from_dict(cfgmod.AppConfig().detector.model_dump()), MS)
print(f"motion_scale={MS}")
trk = Tracker2D("cam0")
pl.preview_client_add("cam0")
_ticks = {"preview_ms": [], "ring_ms": []}
_orig_tick = pl._tick


def _tick(cam, stage, ms):
    if stage in _ticks:
        _ticks[stage].append(ms)
    _orig_tick(cam, stage, ms)


pl._tick = _tick
cap = cv2.VideoCapture("fixtures/synth_basic/cam0.mp4")
acc = {k: [] for k in ("detect", "track", "preview", "ring")}
n = 0
while n < N:
    ok, img = cap.read()
    if not ok:
        break
    t = n / 60.0
    size = (img.shape[1], img.shape[0])
    a = time.perf_counter()
    small = det.shrink(img)
    dets = det.detect(small, n, t, "cam0")
    b = time.perf_counter()
    trk.update(dets, n, t)
    trk.closed()
    c = time.perf_counter()
    # _after_frame does preview (when due) + ring; split its cost with its own timers
    if n % 4 == 0:
        pl._last_enc.pop("cam0", None)
    pl._after_frame("cam0", Frame("cam0", n, t, t, img), t, dets, det, small)
    d = time.perf_counter()
    acc["detect"].append((b - a) * 1000)
    acc["track"].append((c - b) * 1000)
    acc.setdefault("after", []).append((d - c) * 1000)
    n += 1
print(f"frames={n} size={size[0]}x{size[1]}")
tot_mean = tot_med = 0.0
acc["preview"] = _ticks["preview_ms"]
acc["ring"] = _ticks["ring_ms"]
for k in ("detect", "track", "preview", "ring"):
    v = np.array(acc[k])
    print(f"{k:8s} mean {v.mean():7.3f} ms/frame  median {np.median(v):7.3f}")
    tot_mean += v.mean()
    tot_med += np.median(v)
print(f"(after-frame wall incl. bookkeeping: mean {np.mean(acc['after']):.3f} ms)")
print(f"{'sum':8s} mean {tot_mean:7.3f} ms/frame  (median-sum {tot_med:7.3f})")

import sys, time
import cv2, numpy as np
cap = cv2.VideoCapture("fixtures/synth_basic/cam0.mp4")
frames = []
while len(frames) < 100:
    ok, img = cap.read()
    if not ok: break
    frames.append(cv2.resize(img, None, fx=.5, fy=.5, interpolation=cv2.INTER_AREA))
def run(label, mk, prep=lambda f: f, nthreads=1):
    cv2.setNumThreads(nthreads)
    bg = mk(); ts = []
    for f in frames:
        p = prep(f); t0 = time.perf_counter(); bg.apply(p); ts.append(time.perf_counter() - t0)
    print(f"{label:34s} threads={nthreads} mean {np.mean(ts)*1000:6.3f} median {np.median(ts)*1000:6.3f} ms")
base = lambda: cv2.createBackgroundSubtractorMOG2(history=200, varThreshold=25, detectShadows=False)
def nm(n):
    def mk():
        b = base(); b.setNMixtures(n); return b
    return mk
for th in (1, 4, 0):
    run("baseline 5 mixtures", base, nthreads=th)
run("3 mixtures", nm(3))
run("2 mixtures", nm(2))
run("gray 960", base, prep=lambda f: cv2.cvtColor(f, cv2.COLOR_BGR2GRAY))
run("bgr 480", base, prep=lambda f: cv2.resize(f, (480, 270), interpolation=cv2.INTER_AREA))

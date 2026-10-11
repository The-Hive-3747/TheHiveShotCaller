import sys, time, ctypes, threading
sys.path.insert(0, ".")
from hiveshot.ingest import CaptureThread, SourceSpec, SourceKind
fine = "--fine" in sys.argv
if fine: ctypes.windll.winmm.timeBeginPeriod(1)
fx = sys.argv[1]
ths = [CaptureThread(SourceSpec(cam_id=f"c{i}", kind=SourceKind.FILE, target=f"fixtures/{fx}/cam{i}.mp4", realtime=True, loop=False)) for i in (0, 1)]
n = [0, 0]; last = [None, None]; gaps = [0, 0]
def consume(i):
    t = ths[i]
    while True:
        fr = t.get(timeout=0.2)
        if fr is None:
            if t.finished: return
            continue
        n[i] += 1
        if last[i] is not None: gaps[i] += fr.frame_idx - last[i] - 1
        last[i] = fr.frame_idx
        if "--work" in sys.argv:
            import cv2; cv2.resize(fr.image, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
cs = [threading.Thread(target=consume, args=(i,)) for i in (0, 1)]
t0 = time.time()
for t in ths: t.start()
for c in cs: c.start()
for c in cs: c.join()
print("fine" if fine else "default", "wall %.1f" % (time.time() - t0), "got", n, "gaps(dropped)", gaps, "ct.dropped", [t.dropped for t in ths])

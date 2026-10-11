"""Detections of the real ScaledDetector on fixtures, dumped (--save) or compared (--check).
usage: python detect_equiv.py --save|--check [file]"""
import pickle, sys, time
sys.path.insert(0, ".")
import cv2
from hiveshot import pipeline as P
from hiveshot.detect import DetectorConfig
out = {}
t_all = 0.0; nf = 0
for fx in ("synth_240", "synth_20", "synth_basic"):
    for cam in ("cam0", "cam1"):
        cap = cv2.VideoCapture(f"fixtures/{fx}/{cam}.mp4")
        det = P.ScaledDetector(DetectorConfig(), 0.5); res = []
        i = 0
        while True:
            ok, f = cap.read()
            if not ok: break
            t0 = time.perf_counter(); sm = det.shrink(f); d = det.detect(sm, i, i / 60, cam); t_all += time.perf_counter() - t0; nf += 1
            res.append([(x.u, x.v, x.radius_px, x.ball_type.value, x.confidence) for x in d]); i += 1
        out[(fx, cam)] = res
print("mean shrink+detect ms/frame %.3f over %d frames" % (t_all / nf * 1000, nf))
path = sys.argv[2] if len(sys.argv) > 2 else "evidence/m5_perf/detect_ref.pkl"
if sys.argv[1] == "--save":
    pickle.dump(out, open(path, "wb")); print("saved", sum(len(v) for v in out.values()), "frames")
else:
    ref = pickle.load(open(path, "rb")); bad = 0
    for k, v in ref.items():
        for i, (a, b) in enumerate(zip(v, out[k])):
            if a != b: bad += 1; print("DIFF", k, i, a, b) if bad < 5 else None
        assert len(v) == len(out[k])
    print("identical" if not bad else f"{bad} differing frames")

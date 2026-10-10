import json, sys
from pathlib import Path
import cv2, numpy as np
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker")
from hiveshot.detect import BallDetector, DetectorConfig
W, H = 1920, 1080
def run(fx, cam, use_color):
    truth = json.loads((Path(fx)/f"{cam}_truth.json").read_text())
    det = BallDetector(DetectorConfig(use_color=use_color)); cap = cv2.VideoCapture(str(Path(fx)/f"{cam}.mp4"))
    tp=fp=n=0; i=0
    for fr in truth["frames"]:
        ok, frame = cap.read()
        if not ok: break
        dets = det.detect(frame, i, i/truth["fps"], cam); i+=1
        vis=[b for b in fr["balls"] if 0<=b["u"]<W and 0<=b["v"]<H]; n+=len(vis); used=set()
        for d in dets:
            hit=None
            for k,b in enumerate(vis):
                if k not in used and np.hypot(d.u-b["u"], d.v-b["v"])<=6 and abs(d.radius_px-b["radius_px"])<=0.5*b["radius_px"]:
                    hit=k;break
            if hit is None: fp+=1
            else: used.add(hit); tp+=1
    cap.release()
    return tp,fp,n,truth["fps"],len(truth["frames"])
for fx in sys.argv[1:]:
    for cam in ("cam0","cam1"):
        for uc in (True, False):
            tp,fp,n,fps,nf = run(fx,cam,uc)
            print(f"{Path(fx).name} {cam} {'color+motion' if uc else 'motion only'}: truth={n} tp={tp} fp={fp} recall={tp/n:.4f} precision={tp/max(1,tp+fp):.4f} fps={fps} frames={nf}", flush=True)

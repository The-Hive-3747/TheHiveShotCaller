"""Detection recall/precision per view using the PIPELINE's own detector (ScaledDetector + AppConfig default detector settings)."""
import json, sys
from pathlib import Path
import cv2, numpy as np
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker")
from hiveshot import config as cfgmod
from hiveshot.detect import DetectorConfig
from hiveshot.pipeline import ScaledDetector
cfg = cfgmod.AppConfig()
def run(fx, cam):
    truth = json.loads((Path(fx)/f"{cam}_truth.json").read_text()); W = truth["intrinsics"]["width"]; H = truth["intrinsics"]["height"]
    det = ScaledDetector(DetectorConfig.from_dict(cfg.detector.model_dump()), cfg.detector.motion_scale)
    cap = cv2.VideoCapture(str(Path(fx)/f"{cam}.mp4")); tp=fp=n=0
    for i, fr in enumerate(truth["frames"]):
        ok, frame = cap.read()
        if not ok: break
        small = det.shrink(frame); dets = det.detect(small, i, i/truth["fps"], cam)
        vis=[b for b in fr["balls"] if 0<=b["u"]<W and 0<=b["v"]<H]; n+=len(vis); used=set()
        for d in dets:
            hit=None
            for k,b in enumerate(vis):
                if k not in used and np.hypot(d.u-b["u"], d.v-b["v"])<=6 and abs(d.radius_px-b["radius_px"])<=0.5*b["radius_px"]:
                    hit=k;break
            if hit is None: fp+=1
            else: used.add(hit); tp+=1
    cap.release(); return tp,fp,n
for fx in sys.argv[1:]:
    for cam in ("cam0","cam1"):
        tp,fp,n = run(fx,cam)
        print(f"{Path(fx).name} {cam} pipeline-detector: truth={n} tp={tp} fp={fp} recall={tp/n:.4f} precision={tp/max(1,tp+fp):.4f}", flush=True)

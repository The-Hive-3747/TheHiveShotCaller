import json, math, sys
from pathlib import Path
import cv2, numpy as np
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker")
from hiveshot import synth, field
from hiveshot.field_constants import POLLEN_DIAMETER, NECTAR_DIAMETER
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
fps = 60.0
cams = synth.make_default_pair()
offs = [1.0 + o for o in synth._parse_bursts("4,4", 0.3, 3.0)]
trajs, info = synth.build_shots(offs, 777)
kinds = ["pollen" if i % 2 == 0 else "nectar" for i in range(len(trajs))]
for s, k in zip(info, kinds): s["ball_type"] = k
COL = {"pollen": (0, 200, 255), "nectar": (200, 40, 200)}
RAD = {"pollen": POLLEN_DIAMETER / 2, "nectar": NECTAR_DIAMETER / 2}
end = max(off + tr[-1, 0] for off, tr in trajs) + 0.2
n_frames = int(math.ceil(end * fps)) + 1
segs = field.hive_frame_wireframe()
for cam in cams:
    W, H = cam.intr.width, cam.intr.height
    bg = np.full((H, W, 3), 40, np.uint8); synth._draw_wireframe(bg, cam, segs, (150, 150, 150))
    vw = cv2.VideoWriter(str(out / f"{cam.cam_id}.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))
    frames = []
    for fi in range(n_frames):
        t = fi / fps; img = bg.copy(); balls = []
        for bi, (off, tr) in enumerate(trajs):
            p = synth._interp(tr, t - off)
            if p is None: continue
            d = cam.depth(p)[0]
            if d < 1: continue
            u, v = cam.project(p); k = kinds[bi]; rpx = cam.intr.fx * RAD[k] / d
            cv2.circle(img, (int(round(u[0])), int(round(v[0]))), max(1, int(round(rpx))), COL[k], -1, cv2.LINE_AA)
            balls.append({"ball": bi, "xyz": p.tolist(), "u": float(u[0]), "v": float(v[0]), "radius_px": float(rpx)})
        vw.write(img); frames.append({"frame_idx": fi, "t": t, "balls": balls})
    vw.release()
    truth = {"cam_id": cam.cam_id, "fps": fps, "n_frames": n_frames, "ball_radius_in": RAD["pollen"],
             "t_offsets": [float(o) for o, _ in trajs], "intrinsics": cam.intr.__dict__ | {"dist": list(cam.intr.dist)},
             "extrinsics": cam.extr.__dict__ | {"rvec": list(cam.extr.rvec), "tvec": list(cam.extr.tvec)}, "frames": frames}
    (out / f"{cam.cam_id}_truth.json").write_text(json.dumps(truth))
(out / "shots.json").write_text(json.dumps(info, indent=1))
print("kinds", kinds, "made", [s["made"] for s in info])

"""Detection with the REAL printed card (page PNG of tagkit.write_tag_sheet_pdf, cropped inside the dashed cut line, i.e.
including the small 'Label up' text that sits in the top white border) warped onto the projected 7 x 7 in card, from the
documented camera poses with placement error. Compares decode rate / reprojection with the clean generated marker + white border.
Run: PYTHONPATH=. .venv/Scripts/python.exe evidence/refute/dod9_5/printed_card.py [nseeds]"""
import sys
import numpy as np, cv2
sys.path.insert(0, "evidence/refute/dod9_2")
import sim as S
from hiveshot import calib, tagkit
DPI, W0 = 300, 2550
px = 1800; x0 = (W0 - px) // 2; y0 = int(2.1 * DPI); bw = 150
pages = {t: cv2.imread(f"evidence/refute/dod9_5/sheet/tags_p{i+1}.png", 0) for i, t in enumerate((100, 101, 102, 103))}
crops = {t: g[y0 - bw + 5:y0 + px + bw - 4, x0 - bw + 5:x0 + px + bw - 4] for t, g in pages.items()}   # inside the dashed line
def card_quad(cor, border=0.5):
    c = cor.mean(0); r = cor[1] - cor[0]; r /= np.linalg.norm(r); u = cor[0] - cor[3]; u /= np.linalg.norm(u)
    h = np.linalg.norm(cor[1] - cor[0]) / 2 + border
    return np.array([c + h * u - h * r, c + h * u + h * r, c - h * u + h * r, c - h * u - h * r])
def render(cam, tags, mode, seed):
    img = np.full((S.H, S.W), 110, np.uint8)
    for tid, cor in tags.items():
        u, v = cam.project(card_quad(cor)); dst = np.c_[u, v].astype(np.float32)
        if mode == "printed":
            src = crops[tid]
        else:
            n = 1800; b = 150
            src = np.full((n + 2 * b,) * 2, 255, np.uint8); src[b:b + n, b:b + n] = tagkit.render_marker(tid, n)
        h, w = src.shape
        Hm = cv2.getPerspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]), dst)
        wp = cv2.warpPerspective(src, Hm, (S.W, S.H), flags=cv2.INTER_AREA, borderValue=0)
        mk = cv2.warpPerspective(np.full((h, w), 255, np.uint8), Hm, (S.W, S.H)) > 250
        img[mk] = wp[mk]
    rng = np.random.default_rng(seed)
    img = np.clip(img.astype(np.float32) + rng.normal(0, 2, img.shape), 0, 255)
    return cv2.GaussianBlur(img.astype(np.uint8), (3, 3), 0.6)
n = int(sys.argv[1]) if len(sys.argv) > 1 else 15
model = tagkit.tag_defs()
for opt in ("usb", "gopro"):
    for mode in ("generated", "printed"):
        dec = {0: {i: 0 for i in model}, 1: {i: 0 for i in model}}; rp = []
        for s in range(n):
            rng = np.random.default_rng(7000 + s)
            cams = [S.true_cam(opt, "A", rng, "cam0"), S.true_cam(opt, "B", rng, "cam1")]
            for k, cam in enumerate(cams):
                img = np.dstack([render(cam, model, mode, s * 3 + k)] * 3)
                dets = calib.detect_apriltags(img)
                for d in dets:
                    if d["id"] in model: dec[k][d["id"]] += 1
                try:
                    e, inf = calib.solve_extrinsics_from_tags(cam.intr, img, model, f"cam{k}")
                    rp.append(inf["reprojection_px"])
                except ValueError: rp.append(99)
        print(f"{opt:6s} {mode:9s} decoded cam0 {dec[0]} cam1 {dec[1]}  reproj med {np.median(rp):.2f} max {max(rp):.2f}", flush=True)

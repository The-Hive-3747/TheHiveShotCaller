"""Per-camera ball detector: background subtraction + optional HSV color gating."""

from __future__ import annotations

import math
from dataclasses import dataclass, fields
from typing import Any, Optional

import cv2
import numpy as np

from .models import BallType, Detection2D

HSV = tuple[tuple[int, int, int], tuple[int, int, int]]
_ROI_PAD = 4          # px around the motion box: > the reach of the 3x3 open + close


@dataclass
class DetectorConfig:
    min_radius_px: float = 4          # full-resolution pixels
    max_radius_px: float = 60         # full-resolution pixels
    motion_thresh: float = 25
    # VERIFY: OpenCV HSV (H 0-179). Defaults are guesses for the AndyMark balls
    # (POLLEN yellow-ish, NECTAR purple/magenta); tune with real footage.
    pollen_hsv: HSV = ((15, 100, 100), (38, 255, 255))
    nectar_hsv: HSV = ((125, 60, 60), (170, 255, 255))
    use_color: bool = True
    use_motion: bool = True
    bg_history: int = 200
    # MOG2 learning rate. None = 0.001 with color gating (a slow/apex ball is not
    # absorbed into the background; ghosts are removed by the color mask) or the
    # OpenCV automatic rate (~1/bg_history) in motion-only mode, where a slow
    # rate would leave ghosts of anything that was in the first frames.
    bg_learning_rate: Optional[float] = None
    min_circularity: float = 0.6
    process_scale: float = 0.5

    @classmethod
    def from_dict(cls, d: Optional[dict[str, Any]]) -> "DetectorConfig":
        """Build from the app config 'detector' dict; unknown keys are ignored."""
        d = dict(d or {})
        names = {f.name for f in fields(cls)}
        kw = {k: v for k, v in d.items() if k in names}
        for k in ("pollen_hsv", "nectar_hsv"):
            if k in kw:
                lo, hi = kw[k]
                kw[k] = (tuple(int(x) for x in lo), tuple(int(x) for x in hi))
        return cls(**kw)


class BallDetector:
    def __init__(self, config: Optional[DetectorConfig] = None):
        self.cfg = config or DetectorConfig()
        self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        self._bg = None
        self.reset()

    def reset(self) -> None:
        self._bg = cv2.createBackgroundSubtractorMOG2(
            history=self.cfg.bg_history, varThreshold=self.cfg.motion_thresh,
            detectShadows=False)

    def _learning_rate(self) -> Optional[float]:
        """Resolved MOG2 learning rate, or None to use the subtractor's own default."""
        lr = self.cfg.bg_learning_rate
        if lr is None:
            lr = 0.001 if self.cfg.use_color else -1.0
        if isinstance(lr, bool) or not isinstance(lr, (int, float)):
            return None
        return float(lr)

    def _apply_bg(self, small: np.ndarray) -> np.ndarray:
        lr = self._learning_rate()
        if lr is None:
            return self._bg.apply(small)
        try:
            return self._bg.apply(small, learningRate=lr)
        except TypeError:  # wrapper/subtractor whose apply() has no learningRate
            return self._bg.apply(small)

    def _masks(self, small: np.ndarray):
        cfg = self.cfg
        motion = None
        if cfg.use_motion:
            motion = self._apply_bg(small)
        if motion is not None and cfg.use_color:
            return self._gated_masks(small, motion)
        pollen = nectar = None
        if cfg.use_color:
            hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
            pollen = cv2.inRange(hsv, np.array(cfg.pollen_hsv[0], np.uint8),
                                 np.array(cfg.pollen_hsv[1], np.uint8))
            nectar = cv2.inRange(hsv, np.array(cfg.nectar_hsv[0], np.uint8),
                                 np.array(cfg.nectar_hsv[1], np.uint8))
        if motion is not None and pollen is not None:
            color = cv2.bitwise_or(pollen, nectar)
            mask = cv2.bitwise_and(motion, color)
        elif motion is not None:
            mask = motion
        elif pollen is not None:
            mask = cv2.bitwise_or(pollen, nectar)
        else:
            raise ValueError("DetectorConfig: enable use_motion and/or use_color")
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self._kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self._kernel)
        return mask, pollen, nectar

    def _gated_masks(self, small: np.ndarray, motion: np.ndarray):
        """Same masks as the full-frame path for motion & colour gating, but the colour
        conversion, thresholds and morphology only run inside the bounding box of the motion
        mask (the gated mask is zero everywhere else). The box is padded beyond the morphology
        reach so the result is identical to processing the whole frame; a frame without
        motion costs nothing."""
        cfg = self.cfg
        h, w = small.shape[:2]
        mask = np.zeros((h, w), np.uint8)
        pollen = np.zeros((h, w), np.uint8)
        nectar = np.zeros((h, w), np.uint8)
        bx, by, bw, bh = cv2.boundingRect(motion)
        if bw == 0 or bh == 0:
            return mask, pollen, nectar
        x0, y0 = max(0, bx - _ROI_PAD), max(0, by - _ROI_PAD)
        x1, y1 = min(w, bx + bw + _ROI_PAD), min(h, by + bh + _ROI_PAD)
        hsv = cv2.cvtColor(small[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
        pol = cv2.inRange(hsv, np.array(cfg.pollen_hsv[0], np.uint8),
                          np.array(cfg.pollen_hsv[1], np.uint8))
        nec = cv2.inRange(hsv, np.array(cfg.nectar_hsv[0], np.uint8),
                          np.array(cfg.nectar_hsv[1], np.uint8))
        m = cv2.bitwise_and(motion[y0:y1, x0:x1], cv2.bitwise_or(pol, nec))
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, self._kernel)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, self._kernel)
        mask[y0:y1, x0:x1] = m
        pollen[y0:y1, x0:x1] = pol
        nectar[y0:y1, x0:x1] = nec
        return mask, pollen, nectar

    def detect(self, frame_bgr: np.ndarray, frame_idx: int, t: float,
               cam_id: str) -> list[Detection2D]:
        cfg = self.cfg
        s = cfg.process_scale
        if s != 1.0:
            small = cv2.resize(frame_bgr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        else:
            small = frame_bgr
        mask, pollen, nectar = self._masks(small)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        rmin, rmax = cfg.min_radius_px * s, cfg.max_radius_px * s
        out: list[Detection2D] = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < 1:
                continue
            (cx, cy), r = cv2.minEnclosingCircle(c)
            per = cv2.arcLength(c, True)
            circ = min(1.0, 4 * math.pi * area / (per * per)) if per > 0 else 0.0
            if rmin <= r <= rmax and circ >= cfg.min_circularity:
                parts = [(cx, cy, r, circ * min(1.0, area / (math.pi * r * r)))]
            else:
                parts = self._split(c, area, rmin, rmax)
            if not parts:
                continue
            ball_type = BallType.UNKNOWN
            if pollen is not None:
                x, y, w, h = cv2.boundingRect(c)
                blob = np.zeros((h, w), np.uint8)
                cv2.drawContours(blob, [c], -1, 255, -1, offset=(-x, -y))
                np_ = cv2.countNonZero(cv2.bitwise_and(pollen[y:y + h, x:x + w], blob))
                nn = cv2.countNonZero(cv2.bitwise_and(nectar[y:y + h, x:x + w], blob))
                if max(np_, nn) > 0.5 * area:
                    ball_type = BallType.POLLEN if np_ >= nn else BallType.NECTAR
            for px, py, pr, conf in parts:
                out.append(Detection2D(cam_id=cam_id, frame_idx=frame_idx, t=t,
                                       u=px / s, v=py / s, radius_px=pr / s,
                                       ball_type=ball_type, confidence=float(conf)))
        return out

    @staticmethod
    def _split(contour, area: float, rmin: float, rmax: float):
        """Split a touching/overlapping blob into balls using distance-transform
        peaks. Returns [(cx, cy, r, confidence)] in processing-scale pixels."""
        if area < 2 * math.pi * rmin * rmin:
            return []
        x, y, w, h = cv2.boundingRect(contour)
        blob = np.zeros((h + 2, w + 2), np.uint8)
        cv2.drawContours(blob, [contour], -1, 255, -1, offset=(1 - x, 1 - y))
        dist = cv2.distanceTransform(blob, cv2.DIST_L2, 3)
        peaks = ((dist >= cv2.dilate(dist, np.ones((5, 5), np.uint8)) - 1e-6)
                 & (dist >= rmin)).astype(np.uint8)
        n, _, _, cents = cv2.connectedComponentsWithStats(peaks)
        cand = []
        for k in range(1, n):
            px, py = cents[k]
            r = float(dist[int(round(py)), int(round(px))])
            if rmin <= r <= rmax:
                cand.append((r, px + x - 1, py + y - 1))
        cand.sort(reverse=True)
        kept = []
        for r, px, py in cand:
            if all(math.hypot(px - kx, py - ky) >= 0.8 * max(r, kr) for kr, kx, ky in kept):
                kept.append((r, px, py))
        return [(px, py, r, 0.5) for r, px, py in kept]

    @staticmethod
    def draw(frame: np.ndarray, detections: list[Detection2D]) -> np.ndarray:
        img = frame.copy()
        colors = {BallType.POLLEN: (0, 255, 255), BallType.NECTAR: (255, 0, 255),
                  BallType.UNKNOWN: (0, 255, 0)}
        for d in detections:
            col = colors[d.ball_type]
            cv2.circle(img, (int(round(d.u)), int(round(d.v))),
                       max(1, int(round(d.radius_px))), col, 2, cv2.LINE_AA)
            cv2.putText(img, f"{d.ball_type.value} {d.confidence:.2f}",
                        (int(d.u + d.radius_px + 4), int(d.v)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1, cv2.LINE_AA)
        return img


__all__ = ["DetectorConfig", "BallDetector"]

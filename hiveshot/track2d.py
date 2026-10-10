"""Per-camera 2D multi-ball tracker: constant-velocity Kalman + Hungarian assignment."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment

from .models import BallType, Detection2D, Track2D


@dataclass
class Tracker2DConfig:
    # Pixel gates are in the same (full-resolution) coordinates as the detections.
    # The detector already rescales its output to full res, so no process_scale
    # factor is applied here; use `gate_scale` if detections live in another frame.
    max_assoc_px: float = 40.0     # gate around the Kalman prediction (confirmed tracks)
    init_assoc_px: float = 120.0   # gate for a 1-hit track (velocity still unknown)
    max_missed: int = 5
    min_hits: int = 3
    gate_scale: float = 1.0
    process_noise: float = 5.0      # px^2 per frame^4 (accel variance)
    meas_noise: float = 4.0        # px^2


@dataclass
class ActiveTrack(Track2D):
    """Track2D plus bookkeeping. `detections` holds real detections only."""
    predicted: list[tuple[int, float, float]] = field(default_factory=list)  # (frame, u, v)
    missed: int = 0
    closed: bool = False

    @property
    def ball_type(self) -> BallType:
        return majority_ball_type(self.detections)

    @property
    def first_frame(self) -> int:
        return self.detections[0].frame_idx

    @property
    def last_frame(self) -> int:
        return self.detections[-1].frame_idx


def majority_ball_type(dets: list[Detection2D]) -> BallType:
    """Majority vote among known types; UNKNOWN only if no detection has a known type."""
    c = Counter(d.ball_type for d in dets if d.ball_type != BallType.UNKNOWN)
    return c.most_common(1)[0][0] if c else BallType.UNKNOWN


class _KF:
    def __init__(self, u: float, v: float, q: float, r: float):
        kf = cv2.KalmanFilter(4, 2, 0, cv2.CV_64F)
        kf.measurementMatrix = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], np.float64)
        kf.measurementNoiseCov = np.eye(2) * r
        self.q = q
        kf.statePost = np.array([[u], [v], [0.0], [0.0]], np.float64)
        kf.errorCovPost = np.diag([r, r, 400.0, 400.0]).astype(np.float64)
        self.kf = kf

    def predict(self, dt: float) -> tuple[float, float]:
        kf = self.kf
        kf.transitionMatrix = np.array([[1, 0, dt, 0], [0, 1, 0, dt],
                                        [0, 0, 1, 0], [0, 0, 0, 1]], np.float64)
        q = np.zeros((4, 4))
        for a in (0, 1):  # independent u and v axes: [pos, vel] white-acceleration model
            q[a, a] = dt ** 4 / 4
            q[a, a + 2] = q[a + 2, a] = dt ** 3 / 2
            q[a + 2, a + 2] = dt ** 2
        kf.processNoiseCov = q * self.q
        p = kf.predict()
        return float(p[0, 0]), float(p[1, 0])

    def coast(self) -> None:
        self.kf.statePost = self.kf.statePre.copy()
        self.kf.errorCovPost = self.kf.errorCovPre.copy()

    def correct(self, u: float, v: float) -> None:
        self.kf.correct(np.array([[u], [v]], np.float64))

    def init_state(self, u: float, v: float, du: float, dv: float) -> None:
        self.kf.statePost = np.array([[u], [v], [du], [dv]], np.float64)
        self.kf.errorCovPost = np.diag([4.0, 4.0, 25.0, 25.0]).astype(np.float64)


class Tracker2D:
    def __init__(self, cam_id: str = "cam0", config: Optional[Tracker2DConfig] = None):
        self.cam_id = cam_id
        self.cfg = config or Tracker2DConfig()
        self.reset()

    def reset(self) -> None:
        self._tracks: list[ActiveTrack] = []
        self._kfs: dict[int, _KF] = {}
        self._closed: list[ActiveTrack] = []
        self._next_id = 0
        self._last_frame: Optional[int] = None

    def _close(self, tr: ActiveTrack) -> None:
        tr.closed = True
        self._kfs.pop(tr.track_id, None)
        if len(tr.detections) >= self.cfg.min_hits:
            self._closed.append(tr)

    def update(self, detections: list[Detection2D], frame_idx: int, t: float
               ) -> list[Track2D]:
        cfg = self.cfg
        dt = 1.0 if self._last_frame is None else max(1.0, float(frame_idx - self._last_frame))
        self._last_frame = frame_idx
        trs = self._tracks
        preds = [self._kfs[tr.track_id].predict(dt) for tr in trs]

        matched_t: dict[int, int] = {}
        if trs and detections:
            big = 1e9
            cost = np.full((len(trs), len(detections)), big)
            for i, tr in enumerate(trs):
                gate = (cfg.init_assoc_px if len(tr.detections) == 1
                        else cfg.max_assoc_px * (1 + 0.5 * tr.missed)) * cfg.gate_scale
                for j, d in enumerate(detections):
                    dist = float(np.hypot(d.u - preds[i][0], d.v - preds[i][1]))
                    if dist <= gate:
                        cost[i, j] = dist
            ri, ci = linear_sum_assignment(cost)
            for i, j in zip(ri, ci, strict=True):
                if cost[i, j] < big:
                    matched_t[i] = j
        used_d = set(matched_t.values())

        survivors: list[ActiveTrack] = []
        for i, tr in enumerate(trs):
            kf = self._kfs[tr.track_id]
            if i in matched_t:
                d = detections[matched_t[i]]
                first_update = len(tr.detections) == 1
                if first_update:
                    prev = tr.detections[-1]
                    span = max(1.0, float(frame_idx - prev.frame_idx))
                    kf.init_state(d.u, d.v, (d.u - prev.u) / span, (d.v - prev.v) / span)
                else:
                    kf.correct(d.u, d.v)
                tr.detections.append(d)
                tr.missed = 0
                tr.predicted.append((frame_idx, preds[i][0], preds[i][1]))
                survivors.append(tr)
            else:
                kf.coast()
                tr.missed += 1
                tr.predicted.append((frame_idx, preds[i][0], preds[i][1]))
                # tentative tracks die on the first miss; confirmed ones coast
                if len(tr.detections) < cfg.min_hits or tr.missed > cfg.max_missed:
                    self._close(tr)
                else:
                    survivors.append(tr)

        for j, d in enumerate(detections):
            if j in used_d:
                continue
            tid = self._next_id
            self._next_id += 1
            tr = ActiveTrack(cam_id=self.cam_id, track_id=tid, detections=[d])
            self._kfs[tid] = _KF(d.u, d.v, cfg.process_noise, cfg.meas_noise)
            self._kfs[tid].kf.statePre = self._kfs[tid].kf.statePost.copy()
            self._kfs[tid].kf.errorCovPre = self._kfs[tid].kf.errorCovPost.copy()
            survivors.append(tr)

        self._tracks = survivors
        return [tr for tr in survivors if len(tr.detections) >= cfg.min_hits]

    def closed(self) -> list[Track2D]:
        """Pop tracks that finished (reported tracks only)."""
        out, self._closed = self._closed, []
        return out

    def finish(self) -> list[Track2D]:
        """Close all remaining tracks (end of stream) and pop everything closed."""
        for tr in self._tracks:
            self._close(tr)
        self._tracks = []
        return self.closed()

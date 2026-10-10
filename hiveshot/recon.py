"""Two-camera reconstruction: clock sync, track matching, triangulation.

Conventions
-----------
* Time offset: ``t_common = t_cam_b + time_offset_s`` (cam A defines the
  common clock).
* Pixel inputs to ``sampson_distance`` must be *undistorted* pixel coords of
  the ideal pinhole with the original K (see ``calib.undistort_points``);
  ``StereoReconstructor`` does that internally.
* Lengths in inches, time in seconds.

Limitations (read before trusting the numbers)
----------------------------------------------
* ``estimate_time_offset`` uses only coarse event structure (track starts,
  ends, number of simultaneously active tracks).  It needs several
  non-periodic events; a single isolated ball gives a flat/ambiguous
  correlation (low ``confidence``).  Burst spacing that is exactly periodic
  gives aliases at multiples of the period; the track-end times usually break
  the tie.  Track start/end times depend on what each camera can see, so the
  coarse estimate is good to a few ms to tens of ms.  Pass the calibration
  (``StereoReconstructor.refine_time_offset``) to polish it with epipolar
  consistency.
* Epipolar (Sampson) distance is blind to motion along the epipolar line, so
  the refinement only constrains the component of time error that moves a
  ball across epipolar lines.
* Rolling shutter, per-frame exposure-time jitter, and clock drift are not
  modelled (a constant offset is assumed).
* The single-camera fallback is only as accurate as the assumed shot plane
  (launch azimuth); an azimuth error of d degrees displaces a point at
  horizontal range r by about r*sin(d) sideways.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.signal import correlate, savgol_filter

from hiveshot.calib import _rt, camera_matrix, triangulate, undistort_points
from hiveshot.models import (
    CameraExtrinsics,
    CameraIntrinsics,
    Point3D,
    Track2D,
    Track3D,
)

INF = float("inf")


# --------------------------------------------------------------------------
# Epipolar helpers
# --------------------------------------------------------------------------
def _skew(v: np.ndarray) -> np.ndarray:
    return np.array([[0.0, -v[2], v[1]], [v[2], 0.0, -v[0]], [-v[1], v[0], 0.0]])


def fundamental_from_calib(
    intr_a: CameraIntrinsics,
    ext_a: CameraExtrinsics,
    intr_b: CameraIntrinsics,
    ext_b: CameraExtrinsics,
) -> np.ndarray:
    """F such that ``[u_b v_b 1] F [u_a v_a 1]^T = 0`` (undistorted pixels)."""
    Ra, ta = _rt(ext_a)
    Rb, tb = _rt(ext_b)
    R = Rb @ Ra.T
    t = tb - R @ ta
    E = _skew(t) @ R
    Ka, Kb = camera_matrix(intr_a), camera_matrix(intr_b)
    F = np.linalg.inv(Kb).T @ E @ np.linalg.inv(Ka)
    return F / np.linalg.norm(F)


def sampson_distance(F: np.ndarray, uv_a: np.ndarray, uv_b: np.ndarray) -> np.ndarray:
    """First-order geometric epipolar error in pixels (sqrt of the Sampson
    error), for (N,2) undistorted points.  Returns (N,) (or a scalar for 1-D
    input)."""
    single = np.asarray(uv_a).ndim == 1
    a = np.asarray(uv_a, np.float64).reshape(-1, 2)
    b = np.asarray(uv_b, np.float64).reshape(-1, 2)
    xa = np.hstack([a, np.ones((len(a), 1))])
    xb = np.hstack([b, np.ones((len(b), 1))])
    Fxa = xa @ F.T          # F x_a      (N,3)
    Ftxb = xb @ F           # F^T x_b    (N,3)
    num = np.sum(xb * Fxa, axis=1) ** 2
    den = Fxa[:, 0] ** 2 + Fxa[:, 1] ** 2 + Ftxb[:, 0] ** 2 + Ftxb[:, 1] ** 2
    d = np.sqrt(num / np.maximum(den, 1e-30))
    return float(d[0]) if single else d


# --------------------------------------------------------------------------
# Time offset estimation
# --------------------------------------------------------------------------
def _track_arrays(tracks: list[Track2D]) -> list[tuple[float, float]]:
    out = []
    for tr in tracks:
        if tr.detections:
            ts = [d.t for d in tr.detections]
            out.append((min(ts), max(ts)))
    return out


def _activity_signal(
    spans: list[tuple[float, float]], t0: float, n: int, bin_s: float, sigma_s: float
) -> np.ndarray:
    """Smoothed event impulses (starts/ends) plus active-track count."""
    imp = np.zeros(n)
    cnt = np.zeros(n)
    for s, e in spans:
        i0 = int(round((s - t0) / bin_s))
        i1 = int(round((e - t0) / bin_s))
        if 0 <= i0 < n:
            imp[i0] += 1.0
        if 0 <= i1 < n:
            imp[i1] += 1.0
        cnt[max(i0, 0):max(min(i1 + 1, n), 0)] += 1.0
    k = max(1, int(round(3 * sigma_s / bin_s)))
    x = np.arange(-k, k + 1) * bin_s
    g = np.exp(-0.5 * (x / sigma_s) ** 2)
    g /= g.sum()
    imp = np.convolve(imp, g, mode="same")
    cnt = np.convolve(cnt, g, mode="same")
    sig = imp / (imp.max() + 1e-12) + 0.5 * cnt / (cnt.max() + 1e-12)
    return sig - sig.mean()


def _ncc_curve(
    tracks_a: list[Track2D], tracks_b: list[Track2D], bin_s: float, sigma_s: float
):
    """Normalised cross-correlation over all lags; returns (lags, ncc) or None."""
    sa, sb = _track_arrays(tracks_a), _track_arrays(tracks_b)
    if not sa or not sb:
        return None
    t0 = min(min(s for s, _ in sa), min(s for s, _ in sb)) - 0.05
    t1 = max(max(e for _, e in sa), max(e for _, e in sb)) + 0.05
    n = int(np.ceil((t1 - t0) / bin_s)) + 1
    a = _activity_signal(sa, t0, n, bin_s, sigma_s)
    b = _activity_signal(sb, t0, n, bin_s, sigma_s)
    c = correlate(a, b, mode="full", method="fft")
    ones = np.ones(n)
    ea = correlate(a * a, ones, mode="full", method="fft")
    eb = correlate(ones, b * b, mode="full", method="fft")
    ncc = c / np.sqrt(np.maximum(ea * eb, 1e-12))
    lags = np.arange(-(n - 1), n)
    overlap = n - np.abs(lags)
    ncc = ncc * np.clip(overlap / (0.5 * n), 0.0, 1.0)
    return lags, ncc


def _subbin(ncc: np.ndarray, k: int) -> float:
    if 0 < k < len(ncc) - 1:
        y0, y1, y2 = ncc[k - 1], ncc[k], ncc[k + 1]
        den = y0 - 2 * y1 + y2
        if den < 0:
            return float(np.clip(0.5 * (y0 - y2) / den, -1, 1))
    return 0.0


def offset_candidates(
    tracks_a: list[Track2D],
    tracks_b: list[Track2D],
    k: int = 5,
    bin_s: float = 0.005,
    max_lag_s: float = 1.0,
    sigma_s: float = 0.02,
    prior_offset_s: float = 0.0,
    prior_weight: float = 0.1,
    min_sep_s: float = 0.03,
) -> list[tuple[float, float]]:
    """Top-``k`` correlation peaks as ``[(offset_s, score), ...]`` (best first).

    Only lags within ``max_lag_s`` are considered.  score = NCC minus
    ``prior_weight * |offset - prior_offset_s| / max_lag_s``, so the prior only
    decides between near-equal peaks.  Peaks closer than ``min_sep_s`` to a
    better peak are suppressed.
    """
    cur = _ncc_curve(tracks_a, tracks_b, bin_s, sigma_s)
    if cur is None:
        return []
    lags, ncc = cur
    lim = int(round(max_lag_s / bin_s))
    idx = np.flatnonzero(np.abs(lags) <= lim)
    if not len(idx):
        return []
    off = np.empty(len(ncc))
    off[idx] = [(lags[i] + _subbin(ncc, i)) * bin_s for i in idx]
    pen = np.full(len(ncc), -np.inf)
    pen[idx] = ncc[idx] - prior_weight * np.abs(off[idx] - prior_offset_s) / max(max_lag_s, 1e-9)
    # local maxima of the penalised score
    sub = pen[idx]
    loc = [
        i for j, i in enumerate(idx)
        if (j == 0 or sub[j] >= sub[j - 1]) and (j == len(idx) - 1 or sub[j] > sub[j + 1])
    ]
    loc.sort(key=lambda i: -pen[i])
    chosen: list[int] = []
    for i in loc:
        if all(abs(off[i] - off[j]) >= min_sep_s for j in chosen):
            chosen.append(i)
        if len(chosen) >= k:
            break
    return [(float(off[i]), float(pen[i])) for i in chosen]


def estimate_time_offset(
    tracks_a: list[Track2D],
    tracks_b: list[Track2D],
    bin_s: float = 0.005,
    max_lag_s: float = 1.0,
    sigma_s: float = 0.02,
    return_confidence: bool = False,
    prior_offset_s: float = 0.0,
    prior_weight: float = 0.1,
):
    """Offset (s) to add to cam B times to align them with cam A.

    Builds an event/activity signal per camera on ``bin_s`` bins (track start
    and end impulses plus the number of active tracks), cross-correlates them
    (normalised) over lags within ``max_lag_s`` (strictly honoured), refines
    the peak to sub-bin, and returns the best lag.  The peak score is
    penalised by ``prior_weight * |lag - prior_offset_s| / max_lag_s`` so that
    near-equal (aliased) peaks resolve toward the prior (0 for same-PC
    cameras).  With ``return_confidence`` returns ``(offset, confidence)``
    where confidence = best score minus the best score more than 60 ms away
    (0..1).

    Periodic bursts alias at multiples of the shot period; this function alone
    cannot be trusted for them.  Use ``offset_candidates`` +
    ``StereoReconstructor.choose_offset_by_epipolar`` to disambiguate.
    """
    cands = offset_candidates(
        tracks_a, tracks_b, k=50, bin_s=bin_s, max_lag_s=max_lag_s,
        sigma_s=sigma_s, prior_offset_s=prior_offset_s, prior_weight=prior_weight,
        min_sep_s=0.06,
    )
    if not cands:
        return (0.0, 0.0) if return_confidence else 0.0
    best = cands[0]
    second = max((s for o, s in cands[1:] if abs(o - best[0]) > 0.06), default=0.0)
    conf = float(np.clip(best[1] - max(second, 0.0), 0.0, 1.0))
    return (best[0], conf) if return_confidence else best[0]



# --------------------------------------------------------------------------
# Stereo reconstruction
# --------------------------------------------------------------------------
def _arr(track: Track2D) -> tuple[np.ndarray, np.ndarray]:
    dets = sorted(track.detections, key=lambda d: d.t)
    t = np.array([d.t for d in dets], np.float64)
    uv = np.array([[d.u, d.v] for d in dets], np.float64).reshape(-1, 2)
    return t, uv


def _fragment_ok(a: Track2D, b: Track2D, gap_s: float, px: float) -> bool:
    """True if ``b`` plausibly continues ``a`` (same camera): starts within
    ``gap_s`` after ``a`` ends and sits near a constant-velocity extrapolation
    of ``a``'s tail.  Tolerance grows with the gap: ``px * (1 + gap / 0.1 s)``."""
    ta, uva = _arr(a)
    tb, uvb = _arr(b)
    gap = float(tb[0] - ta[-1])
    if gap < 0.0 or gap > gap_s + 1e-9:
        return False
    k = min(4, len(ta))
    if k >= 2 and ta[-1] > ta[-k]:
        vel = (uva[-1] - uva[-k]) / (ta[-1] - ta[-k])
    else:
        vel = np.zeros(2)
    pred = uva[-1] + vel * gap
    tol = px * (1.0 + gap / 0.1)
    return float(np.linalg.norm(pred - uvb[0])) <= tol


def merge_fragments(tracks: list[Track2D], gap_s: float = 0.25, px: float = 40.0) -> list[Track2D]:
    """Join same-camera tracks that are fragments of one flight (brief
    detection dropout).  A track is appended to another if it starts within
    ``gap_s`` after it ends and matches a constant-velocity pixel
    extrapolation within ``px`` (scaled up with the gap).  Each track is used
    as predecessor/successor at most once.  Merged tracks get fresh
    ``track_id`` values (above all inputs) with detections sorted by time;
    untouched tracks are returned as the original objects."""
    if gap_s <= 0.0 or len(tracks) < 2:
        return list(tracks)
    idx = [i for i, t in enumerate(tracks) if t.detections]
    cand = []
    for i in idx:
        for j in idx:
            if i != j and _fragment_ok(tracks[i], tracks[j], gap_s, px):
                ta, _ = _arr(tracks[i])
                tb, _ = _arr(tracks[j])
                cand.append((float(tb[0] - ta[-1]), i, j))
    cand.sort()
    nxt: dict[int, int] = {}
    prv: dict[int, int] = {}
    for _, i, j in cand:
        if i in nxt or j in prv:
            continue
        k = i
        while k in prv:
            k = prv[k]
        if k == j:
            continue
        nxt[i], prv[j] = j, i
    next_id = max((t.track_id for t in tracks), default=-1) + 1
    out: list[Track2D] = []
    for i, t in enumerate(tracks):
        if i in prv:
            continue
        if i not in nxt:
            out.append(t)
            continue
        dets = list(t.detections)
        k = i
        while k in nxt:
            k = nxt[k]
            dets.extend(tracks[k].detections)
        dets.sort(key=lambda d: d.t)
        out.append(Track2D(t.cam_id, next_id, dets))
        next_id += 1
    return out


@dataclass
class _PairEval:
    t: np.ndarray        # cam A times used
    uv_a: np.ndarray     # raw pixels
    uv_b: np.ndarray     # interpolated raw pixels
    ok: np.ndarray       # bool mask: within B span and max_dt


class StereoReconstructor:
    def __init__(
        self,
        intr_a: CameraIntrinsics,
        ext_a: CameraExtrinsics,
        intr_b: CameraIntrinsics,
        ext_b: CameraExtrinsics,
        time_offset_s: float = 0.0,
        max_residual_in: float = 3.0,
        max_dt_s: float = 1.0 / 120.0,
        max_epipolar_px: float = 4.0,
        min_overlap_pts: int = 5,
        smooth: bool = False,
        smooth_window: int = 5,
        smooth_order: int = 2,
        merge_gap_s: float = 0.25,
        merge_px: float = 40.0,
    ):
        self.intr_a, self.ext_a = intr_a, ext_a
        self.intr_b, self.ext_b = intr_b, ext_b
        self.time_offset_s = float(time_offset_s)
        self.max_residual_in = max_residual_in
        self.max_dt_s = max_dt_s
        self.max_epipolar_px = max_epipolar_px
        self.min_overlap_pts = min_overlap_pts
        self.smooth = smooth
        self.smooth_window = smooth_window
        self.smooth_order = smooth_order
        self.merge_gap_s = merge_gap_s
        self.merge_px = merge_px
        self.F = fundamental_from_calib(intr_a, ext_a, intr_b, ext_b)
        self.last_choice_confidence = 0.0

    # -- internals ---------------------------------------------------------
    def _evaluate(self, track_a: Track2D, track_b: Track2D) -> Optional[_PairEval]:
        if not track_a.detections or not track_b.detections:
            return None
        ta, uva = _arr(track_a)
        tb, uvb = _arr(track_b)
        tb = tb + self.time_offset_s
        inside = (ta >= tb[0]) & (ta <= tb[-1])
        if not inside.any():
            return None
        u = np.interp(ta, tb, uvb[:, 0])
        v = np.interp(ta, tb, uvb[:, 1])
        j = np.clip(np.searchsorted(tb, ta), 1, len(tb) - 1) if len(tb) > 1 else np.zeros(len(ta), int)
        near = np.minimum(np.abs(ta - tb[j]), np.abs(ta - tb[np.maximum(j - 1, 0)]))
        ok = inside & (near <= self.max_dt_s + 1e-6)
        return _PairEval(ta, uva, np.column_stack([u, v]), ok)

    def pair_cost(self, track_a: Track2D, track_b: Track2D) -> float:
        """Mean Sampson distance (px) over time-aligned samples; inf if the
        tracks overlap in fewer than ``min_overlap_pts`` samples."""
        ev = self._evaluate(track_a, track_b)
        if ev is None or int(ev.ok.sum()) < self.min_overlap_pts:
            return INF
        ua = undistort_points(self.intr_a, ev.uv_a[ev.ok])
        ub = undistort_points(self.intr_b, ev.uv_b[ev.ok])
        return float(np.mean(sampson_distance(self.F, ua, ub)))

    def cost_matrix(self, tracks_a: list[Track2D], tracks_b: list[Track2D]) -> np.ndarray:
        return self._fast_cost_matrix(
            self._prep(tracks_a, self.intr_a), self._prep(tracks_b, self.intr_b),
            self.time_offset_s,
        )

    def match_tracks(
        self, tracks_a: list[Track2D], tracks_b: list[Track2D]
    ) -> list[tuple[Track2D, Track2D]]:
        """Hungarian assignment on mean Sampson distance, gated at
        ``max_epipolar_px`` and on the median 3D residual.  Same-camera
        fragments of one flight are merged first (``merge_fragments``), so the
        returned tracks may be merged Track2D objects."""
        if not tracks_a or not tracks_b:
            return []
        tracks_a = merge_fragments(tracks_a, self.merge_gap_s, self.merge_px)
        tracks_b = merge_fragments(tracks_b, self.merge_gap_s, self.merge_px)
        C = self.cost_matrix(tracks_a, tracks_b)
        big = 1e6
        Cg = np.where(np.isfinite(C) & (C <= self.max_epipolar_px), C, big)
        rows, cols = linear_sum_assignment(Cg)
        out = []
        for i, j in zip(rows, cols, strict=True):
            if Cg[i, j] >= big:
                continue
            tr3 = self.reconstruct(tracks_a[i], tracks_b[j])
            if len(tr3.points) < self.min_overlap_pts:
                continue
            if float(np.median([p.residual_in for p in tr3.points])) > self.max_residual_in:
                continue
            out.append((tracks_a[i], tracks_b[j]))
        return out

    def reconstruct(self, track_a: Track2D, track_b: Track2D) -> Track3D:
        out = Track3D(track_id=track_a.track_id)
        ev = self._evaluate(track_a, track_b)
        if ev is None or not ev.ok.any():
            return out
        t = ev.t[ev.ok]
        xyz, res = triangulate(
            self.intr_a, self.ext_a, ev.uv_a[ev.ok],
            self.intr_b, self.ext_b, ev.uv_b[ev.ok],
        )
        keep = np.isfinite(xyz).all(axis=1) & (res <= self.max_residual_in)
        t, xyz, res = t[keep], xyz[keep], res[keep]
        if self.smooth and len(t) >= self.smooth_window:
            xyz = savgol_filter(xyz, self.smooth_window, self.smooth_order, axis=0)
        bt = track_a.detections[0].ball_type
        out.ball_type = bt
        out.points = [
            Point3D(float(ti), float(p[0]), float(p[1]), float(p[2]), float(r))
            for ti, p, r in zip(t, xyz, res, strict=True)
        ]
        return out

    def reconstruct_all(
        self, tracks_a: list[Track2D], tracks_b: list[Track2D]
    ) -> list[Track3D]:
        return [self.reconstruct(a, b) for a, b in self.match_tracks(tracks_a, tracks_b)]

    def refine_time_offset(
        self,
        tracks_a: list[Track2D],
        tracks_b: list[Track2D],
        window_s: float = 0.05,
        step_s: float = 0.001,
    ) -> float:
        """Polish ``self.time_offset_s`` by minimising the mean matched
        Sampson distance within +/-window_s of the current value.  Sets and
        returns the new offset (unchanged if nothing matches)."""
        base = self.time_offset_s
        best, best_cost = base, INF
        for off in np.arange(base - window_s, base + window_s + 1e-9, step_s):
            self.time_offset_s = float(off)
            C = self.cost_matrix(tracks_a, tracks_b)
            Cg = np.where(np.isfinite(C) & (C <= 5 * self.max_epipolar_px), C, 1e6)
            r, c = linear_sum_assignment(Cg)
            good = [Cg[i, j] for i, j in zip(r, c, strict=True) if Cg[i, j] < 1e6]
            if len(good) < max(1, min(len(tracks_a), len(tracks_b)) // 2):
                continue
            cost = float(np.mean(good))
            if cost < best_cost:
                best, best_cost = float(off), cost
        self.time_offset_s = best
        return best


    # -- fast cost evaluation (precomputed, undistorted) -------------------
    def _prep(self, tracks: list[Track2D], intr: CameraIntrinsics):
        out = []
        for tr in tracks:
            if not tr.detections:
                out.append(None)
                continue
            t, uv = _arr(tr)
            out.append((t, undistort_points(intr, uv)))
        return out

    def _fast_cost_matrix(self, pa, pb, offset: float) -> np.ndarray:
        C = np.full((len(pa), len(pb)), INF)
        for i, a in enumerate(pa):
            if a is None:
                continue
            ta, ua = a
            for j, b in enumerate(pb):
                if b is None:
                    continue
                tb = b[0] + offset
                inside = (ta >= tb[0]) & (ta <= tb[-1])
                if int(inside.sum()) < self.min_overlap_pts:
                    continue
                t = ta[inside]
                k = np.clip(np.searchsorted(tb, t), 1, max(len(tb) - 1, 1))
                near = np.minimum(np.abs(t - tb[np.minimum(k, len(tb) - 1)]), np.abs(t - tb[k - 1]))
                ok = near <= self.max_dt_s + 1e-6
                if int(ok.sum()) < self.min_overlap_pts:
                    continue
                t = t[ok]
                ub = np.column_stack(
                    [np.interp(t, tb, b[1][:, 0]), np.interp(t, tb, b[1][:, 1])]
                )
                C[i, j] = float(np.mean(sampson_distance(self.F, ua[inside][ok], ub)))
        return C

    def _assignment_cost(self, C: np.ndarray) -> float:
        """Mean per-track cost of the gated assignment; every unmatched track
        (of the smaller side) costs the gate ``max_epipolar_px``."""
        g = self.max_epipolar_px
        n = min(C.shape)
        if n == 0:
            return INF
        Cg = np.where(np.isfinite(C) & (C <= g), C, 1e6)
        r, c = linear_sum_assignment(Cg)
        good = [Cg[i, j] for i, j in zip(r, c, strict=True) if Cg[i, j] < 1e6]
        return float((sum(good) + g * (n - len(good))) / n)

    def choose_offset_by_epipolar(
        self,
        tracks_a: list[Track2D],
        tracks_b: list[Track2D],
        candidates: list[float],
        probe_s: float = 0.012,
        probe_step_s: float = 0.004,
        fine_s: float = 0.008,
        fine_step_s: float = 0.001,
    ) -> tuple[float, float]:
        """Pick, among candidate offsets (e.g. from ``offset_candidates``),
        the one with the lowest assignment cost (mean Sampson px of the gated
        Hungarian matching, unmatched tracks costing the gate).  Each candidate
        is probed over +/-``probe_s``, the winner is then refined on a fine
        grid.  Sets ``self.time_offset_s`` and returns ``(offset, cost)``;
        ``self.last_choice_confidence`` holds a 0..1 confidence from the
        margin to the best candidate more than 60 ms away."""
        self.last_choice_confidence = 0.0
        cands = [float(c) for c in candidates]
        if not cands:
            return self.time_offset_s, INF
        ta = merge_fragments(tracks_a, self.merge_gap_s, self.merge_px)
        tb = merge_fragments(tracks_b, self.merge_gap_s, self.merge_px)
        pa, pb = self._prep(ta, self.intr_a), self._prep(tb, self.intr_b)

        def best_near(c: float, half: float, step: float):
            best = (INF, c)
            for off in np.arange(c - half, c + half + 1e-9, step):
                cost = self._assignment_cost(self._fast_cost_matrix(pa, pb, float(off)))
                if cost < best[0]:
                    best = (cost, float(off))
            return best

        res = [best_near(c, probe_s, probe_step_s) for c in cands]
        win = min(range(len(res)), key=lambda i: res[i][0])
        cost, off = best_near(res[win][1], fine_s, fine_step_s)
        others = [r[0] for r, c in zip(res, cands, strict=True)
                  if abs(c - cands[win]) > 0.06]
        if others:
            c2 = min(others)
            self.last_choice_confidence = float(np.clip((c2 - cost) / max(c2, 1e-9), 0, 1))
        else:
            self.last_choice_confidence = 1.0 if cost < self.max_epipolar_px else 0.0
        self.time_offset_s = off
        return off, cost

# --------------------------------------------------------------------------
# Single camera fallback
# --------------------------------------------------------------------------
def plane_from_launch(
    launch_point: tuple[float, float, float], azimuth_deg: float
) -> tuple[np.ndarray, np.ndarray]:
    """Vertical plane through ``launch_point`` whose horizontal direction is
    ``azimuth_deg`` (from +X toward +Y).  Returns (point, normal)."""
    az = np.deg2rad(azimuth_deg)
    n = np.array([-np.sin(az), np.cos(az), 0.0])
    return np.asarray(launch_point, np.float64), n


class SingleCameraFallback:
    """3D from one camera by intersecting viewing rays with an assumed
    vertical shot plane.  Accuracy depends on the azimuth assumption (see
    module docstring) and degrades when the ray is nearly parallel to the
    plane (such points are dropped)."""

    def __init__(self, min_cos: float = 0.05):
        self.min_cos = min_cos

    def reconstruct_with_plane(
        self,
        track: Track2D,
        intr: CameraIntrinsics,
        ext: CameraExtrinsics,
        plane_point: np.ndarray,
        plane_normal: np.ndarray,
    ) -> Track3D:
        out = Track3D(track_id=track.track_id)
        if not track.detections:
            return out
        dets = sorted(track.detections, key=lambda d: d.t)
        uv = np.array([[d.u, d.v] for d in dets], np.float64)
        nrm = undistort_points(intr, uv, True)
        R, tv = _rt(ext)
        C = -R.T @ tv
        d = np.hstack([nrm, np.ones((len(nrm), 1))]) @ R   # R^T [x y 1]
        d /= np.linalg.norm(d, axis=1, keepdims=True)
        n = np.asarray(plane_normal, np.float64)
        n = n / np.linalg.norm(n)
        p0 = np.asarray(plane_point, np.float64)
        denom = d @ n
        num = float(n @ (p0 - C))
        with np.errstate(divide="ignore", invalid="ignore"):
            s = num / denom
        valid = (np.abs(denom) > self.min_cos) & (s > 0)
        out.ball_type = dets[0].ball_type
        for det, ok, si, di in zip(dets, valid, s, d, strict=True):
            if not ok:
                continue
            p = C + si * di
            out.points.append(Point3D(det.t, float(p[0]), float(p[1]), float(p[2]), 0.0))
        return out


def reconstruct_with_plane(
    track: Track2D,
    intr: CameraIntrinsics,
    ext: CameraExtrinsics,
    plane_point: np.ndarray,
    plane_normal: np.ndarray,
) -> Track3D:
    """Module-level convenience for ``SingleCameraFallback``."""
    return SingleCameraFallback().reconstruct_with_plane(
        track, intr, ext, plane_point, plane_normal
    )

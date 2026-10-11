"""Tests for hiveshot.recon using the synth_basic fixture truth."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from hiveshot.calib import project
from hiveshot.models import (
    CameraExtrinsics,
    CameraIntrinsics,
    Detection2D,
    Track2D,
)
from hiveshot.recon import (
    StereoReconstructor,
    estimate_time_offset,
    fundamental_from_calib,
    merge_fragments,
    plane_from_launch,
    reconstruct_with_plane,
    sampson_distance,
)

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures" / "synth_basic"
EVID = ROOT / "evidence" / "m3_recon"
SHIFT = 0.137
NOISE_PX = 0.3


def _load(cam: str, fix: Path = FIX):
    d = json.loads((fix / f"{cam}_truth.json").read_text())
    i = d["intrinsics"]
    intr = CameraIntrinsics(**{**i, "dist": tuple(i["dist"])})
    e = d["extrinsics"]
    ext = CameraExtrinsics(**{**e, "rvec": tuple(e["rvec"]), "tvec": tuple(e["tvec"])})
    return d, intr, ext


def _tracks(d, intr, rng, shift=0.0, noise=NOISE_PX):
    """Track2D per truth ball id (track_id == shot id); in-frame points only."""
    per: dict[int, list[Detection2D]] = {}
    truth: dict[tuple[int, int], list[float]] = {}
    for f in d["frames"]:
        for b in f["balls"]:
            u = b["u"] + rng.normal(0, noise)
            v = b["v"] + rng.normal(0, noise)
            truth[(b["ball"], f["frame_idx"])] = b["xyz"]
            if not (0 <= u < intr.width and 0 <= v < intr.height):
                continue
            per.setdefault(b["ball"], []).append(
                Detection2D(d["cam_id"], f["frame_idx"], f["t"] + shift, u, v, b["radius_px"])
            )
    tracks = [Track2D(d["cam_id"], k, v) for k, v in sorted(per.items())]
    return tracks, truth


def _truth_plane(truth, ball: int):
    """True vertical shot plane of a ball, from its own truth trajectory:
    launch point = first truth point, azimuth = horizontal direction of the
    flight (drag-free fixtures fly in a vertical plane).  Derived from the
    truth JSON rather than shots.json so it cannot go stale relative to it."""
    frames = sorted(k for b, k in truth if b == ball)
    p0 = np.array(truth[(ball, frames[0])])
    p1 = np.array(truth[(ball, frames[min(10, len(frames) - 1)])])
    az = np.degrees(np.arctan2(p1[1] - p0[1], p1[0] - p0[0]))
    return plane_from_launch(tuple(p0), az)


@pytest.fixture(scope="module")
def setup():
    rng = np.random.default_rng(12345)
    d0, i0, e0 = _load("cam0")
    d1, i1, e1 = _load("cam1")
    ta, truth = _tracks(d0, i0, rng)
    tb, _ = _tracks(d1, i1, rng, shift=SHIFT)
    return dict(i0=i0, e0=e0, i1=i1, e1=e1, ta=ta, tb=tb, truth=truth)


def _recon(s, offset=-SHIFT, **kw):
    return StereoReconstructor(s["i0"], s["e0"], s["i1"], s["e1"], time_offset_s=offset, **kw)


def test_time_offset_recovered(setup):
    off, conf = estimate_time_offset(setup["ta"], setup["tb"], return_confidence=True)
    assert abs(off + SHIFT) < 0.010, (off, conf)
    assert conf > 0.0
    rec = _recon(setup, offset=off)
    ref = rec.refine_time_offset(setup["ta"], setup["tb"])
    assert abs(ref + SHIFT) < 0.010


def test_time_offset_empty():
    assert estimate_time_offset([], []) == 0.0


def test_fundamental_epipolar_constraint(setup):
    F = fundamental_from_calib(setup["i0"], setup["e0"], setup["i1"], setup["e1"])
    xyz = np.array([[0.0, 0.0, 20.0], [10.0, -20.0, 40.0], [-30.0, 40.0, 60.0]])
    ua = project(setup["i0"], setup["e0"], xyz)
    ub = project(setup["i1"], setup["e1"], xyz)
    assert np.all(sampson_distance(F, ua, ub) < 1e-6)
    assert np.all(sampson_distance(F, ua, ub + [20.0, 20.0]) > 1.0)


def test_match_all_six_shots(setup):
    pairs = _recon(setup).match_tracks(setup["ta"], setup["tb"])
    assert len(pairs) == 6
    assert all(a.track_id == b.track_id for a, b in pairs)
    assert {a.track_id for a, _ in pairs} == set(range(6))


def test_match_robust_to_list_order(setup):
    pairs = _recon(setup).match_tracks(setup["ta"], list(reversed(setup["tb"])))
    assert len(pairs) == 6 and all(a.track_id == b.track_id for a, b in pairs)


def test_reconstruct_accuracy(setup):
    rec = _recon(setup)
    errs, resid = [], []
    for tr3 in rec.reconstruct_all(setup["ta"], setup["tb"]):
        by_t = {round(d.t, 6): d.frame_idx for d in setup["ta"][tr3.track_id].detections}
        assert len(tr3.points) > 20
        for p in tr3.points:
            truth = np.array(setup["truth"][(tr3.track_id, by_t[round(p.t, 6)])])
            errs.append(np.linalg.norm(np.array([p.x, p.y, p.z]) - truth))
            resid.append(p.residual_in)
    errs = np.array(errs)
    rms = float(np.sqrt(np.mean(errs**2)))
    assert rms < 0.75
    assert 0.0 < max(resid) <= 3.0

    est, conf = estimate_time_offset(setup["ta"], setup["tb"], return_confidence=True)
    refined = _recon(setup, offset=est).refine_time_offset(setup["ta"], setup["tb"])
    EVID.mkdir(parents=True, exist_ok=True)
    (EVID / "accuracy.txt").write_text(
        f"points: {len(errs)}\n"
        f"3D RMS error (in): {rms:.4f}\n"
        f"3D max error (in): {errs.max():.4f}\n"
        f"3D median error (in): {np.median(errs):.4f}\n"
        f"mean residual (in): {np.mean(resid):.4f}  max residual (in): {max(resid):.4f}\n"
        f"noise: {NOISE_PX} px gaussian; cam1 shifted by +{SHIFT} s\n"
        f"true offset (s): {-SHIFT:.4f}\n"
        f"coarse estimate (s): {est:.4f}  error (ms): {1000 * (est + SHIFT):+.2f}  "
        f"confidence: {conf:.3f}\n"
        f"epipolar-refined estimate (s): {refined:.4f}  error (ms): "
        f"{1000 * (refined + SHIFT):+.2f}\n",
        encoding="utf-8",
    )


def test_savgol_option(setup):
    trs = _recon(setup, smooth=True).reconstruct_all(setup["ta"], setup["tb"])
    assert len(trs) == 6 and all(len(t.points) > 20 for t in trs)


def test_bad_pairing_rejected(setup):
    rec = _recon(setup)
    a1 = next(t for t in setup["ta"] if t.track_id == 1)
    b3 = next(t for t in setup["tb"] if t.track_id == 3)
    assert rec.pair_cost(a1, b3) > rec.max_epipolar_px
    assert rec.match_tracks([a1], [b3]) == []
    b1 = next(t for t in setup["tb"] if t.track_id == 1)
    assert len(rec.match_tracks([a1], [b1])) == 1
    far = Track2D(
        "cam1", 99,
        [Detection2D("cam1", i, 50.0 + i / 60, 900.0, 500.0, 20.0) for i in range(30)],
    )
    assert rec.pair_cost(a1, far) == float("inf")
    assert rec.match_tracks([a1], [far]) == []


def test_plane_fallback_matches_truth_noisy(setup):
    for intr, ext, tracks in (
        (setup["i0"], setup["e0"], setup["ta"]),
        (setup["i1"], setup["e1"], setup["tb"]),
    ):
        for tr in tracks:
            pp, pn = _truth_plane(setup["truth"], tr.track_id)
            tr3 = reconstruct_with_plane(tr, intr, ext, pp, pn)
            assert len(tr3.points) > 10
            # frame index is not recoverable after the +SHIFT on cam1, so
            # compare by time (cam1 times carry the shift).
            shift = SHIFT if tr.cam_id == "cam1" else 0.0
            for p in tr3.points[::7]:
                k = int(round((p.t - shift) * 60))
                truth = np.array(setup["truth"][(tr.track_id, k)])
                assert np.linalg.norm(np.array([p.x, p.y, p.z]) - truth) < 1.0


def test_plane_fallback_noise_free_exact():
    d0, i0, e0 = _load("cam0")
    tracks, truth = _tracks(d0, i0, np.random.default_rng(0), noise=0.0)
    worst = 0.0
    for tr in tracks:
        pp, pn = _truth_plane(truth, tr.track_id)
        tr3 = reconstruct_with_plane(tr, i0, e0, pp, pn)
        by_t = {round(d.t, 6): d.frame_idx for d in tr.detections}
        for p in tr3.points:
            t = np.array(truth[(tr.track_id, by_t[round(p.t, 6)])])
            worst = max(worst, float(np.linalg.norm(np.array([p.x, p.y, p.z]) - t)))
    assert worst < 1e-3


def test_two_simultaneous_balls_not_crossed(setup):
    i0, e0, i1, e1 = setup["i0"], setup["e0"], setup["i1"], setup["e1"]
    rng = np.random.default_rng(7)
    g = 386.1
    t = np.arange(0, 0.9, 1 / 60)

    def make(p0, v0, tid):
        xyz = np.array(
            [[p0[0] + v0[0] * s, p0[1] + v0[1] * s, p0[2] + v0[2] * s - 0.5 * g * s * s] for s in t]
        )
        out = []
        for intr, ext, cam, sh in ((i0, e0, "cam0", 0.0), (i1, e1, "cam1", SHIFT)):
            uv = project(intr, ext, xyz) + rng.normal(0, NOISE_PX, (len(t), 2))
            out.append(Track2D(cam, tid, [
                Detection2D(cam, k, float(tk + sh), float(p[0]), float(p[1]), 20.0)
                for k, (tk, p) in enumerate(zip(t, uv, strict=True))
            ]))
        return out, xyz

    (a1, b1), x1 = make((-10.0, 60.0, 12.0), (0.0, -30.0, 270.0), 1)
    (a2, b2), x2 = make((-4.0, 62.0, 12.0), (-10.0, -25.0, 275.0), 2)
    ta, tb = [a1, a2], [b2, b1]  # B order swapped on purpose
    rec = StereoReconstructor(i0, e0, i1, e1, time_offset_s=-SHIFT)
    pairs = rec.match_tracks(ta, tb)
    assert len(pairs) == 2
    for a, b in pairs:
        assert a.track_id == b.track_id
    for tr3, x in zip(rec.reconstruct_all(ta, tb), (x1, x2), strict=True):
        assert len(tr3.points) > 20
        err = [np.linalg.norm([p.x, p.y, p.z] - x[int(round(p.t * 60))]) for p in tr3.points]
        assert np.sqrt(np.mean(np.square(err))) < 0.75


def test_burst_fixture_match_and_offset():
    """synth_burst: 4 shots 0.3 s apart, 3 s gap, 2 more (periodic burst)."""
    fix = ROOT / "fixtures" / "synth_burst"
    rng = np.random.default_rng(99)
    d0, i0, e0 = _load("cam0", fix)
    d1, i1, e1 = _load("cam1", fix)
    ta, _ = _tracks(d0, i0, rng)
    tb, _ = _tracks(d1, i1, rng, shift=SHIFT)
    assert len(ta) == 6 and len(tb) == 6
    off = estimate_time_offset(ta, tb)
    assert abs(off + SHIFT) < 0.010, off
    rec = StereoReconstructor(i0, e0, i1, e1, time_offset_s=-SHIFT)
    pairs = rec.match_tracks(ta, tb)
    assert len(pairs) == 6
    assert all(a.track_id == b.track_id for a, b in pairs)


def test_split_track_still_reconstructs_full_flight(setup):
    tb = []
    for t in setup["tb"]:
        if t.track_id == 2:
            dets = sorted(t.detections, key=lambda d: d.t)
            m = len(dets) // 2
            first, second = dets[: m - 2], dets[m + 2 :]  # 4 frames removed
            tb.append(Track2D("cam1", 2, first))
            tb.append(Track2D("cam1", 100, second))
        else:
            tb.append(t)
    rec = _recon(setup)
    trs = rec.reconstruct_all(setup["ta"], tb)
    assert len(trs) == 6
    shot2 = next(t for t in trs if t.track_id == 2)
    truth_n = len(next(t for t in setup["ta"] if t.track_id == 2).detections)
    assert len(shot2.points) >= 0.9 * truth_n
    # without merging the second half is lost
    nomerge = _recon(setup, merge_gap_s=0.0).reconstruct_all(setup["ta"], tb)
    assert len(next(t for t in nomerge if t.track_id == 2).points) < 0.9 * truth_n


def test_merge_fragments_rejects_distant_balls():
    def trk(tid, t0, u0, n=10):
        return Track2D("cam0", tid, [
            Detection2D("cam0", k, t0 + k / 60, u0, 300.0, 20.0) for k in range(n)
        ])

    a = trk(1, 0.0, 200.0)
    b = trk(2, 9 / 60 + 0.1, 500.0)  # starts 0.1 s after a ends, 300 px away
    out = merge_fragments([a, b], 0.25, 40.0)
    assert len(out) == 2
    # control: same position continues -> merged, sorted, fresh id
    c = trk(3, 9 / 60 + 0.1, 200.0)
    out = merge_fragments([c, a], 0.25, 40.0)
    assert len(out) == 1 and len(out[0].detections) == 20
    ts = [d.t for d in out[0].detections]
    assert ts == sorted(ts) and out[0].track_id not in (1, 3)


def _synth20(shift: float, seed: int = 5):
    fix = ROOT / "fixtures" / "synth_20"
    rng = np.random.default_rng(seed)
    d0, i0, e0 = _load("cam0", fix)
    d1, i1, e1 = _load("cam1", fix)
    ta, _ = _tracks(d0, i0, rng)
    tb, _ = _tracks(d1, i1, rng, shift=shift)
    return ta, tb, StereoReconstructor(i0, e0, i1, e1)


@pytest.mark.parametrize("shift", [0.0, SHIFT])
def test_periodic_bursts_alias_robust(shift):
    """20 shots, 0.25 s spacing, bursts of 4 with 3 s gaps: the raw
    correlation alone may lock on a one-period alias; the epipolar choice
    over the top-5 peaks must not."""
    from hiveshot.recon import offset_candidates

    ta, tb, rec = _synth20(shift)
    assert len(ta) == 20 and len(tb) == 20
    cands = offset_candidates(ta, tb, k=5)
    assert 1 < len(cands) <= 5
    off, cost = rec.choose_offset_by_epipolar(ta, tb, [o for o, _ in cands])
    assert abs(off + shift) < 0.010, (off, cost, cands)
    assert cost < rec.max_epipolar_px
    assert rec.last_choice_confidence > 0.3
    assert len(rec.match_tracks(ta, tb)) == 20


def test_alias_candidate_loses_to_true_offset():
    ta, tb, rec = _synth20(0.0)
    off, cost = rec.choose_offset_by_epipolar(ta, tb, [-0.25, 0.25, 0.5])
    # none of the candidates is true; they must all cost much more than truth
    _, true_cost = rec.choose_offset_by_epipolar(ta, tb, [0.0])
    assert true_cost < 1.0 < cost


def test_max_lag_and_prior_honoured():
    ta, tb, _ = _synth20(0.0)
    for lag in (0.05, 0.1, 0.3):
        off = estimate_time_offset(ta, tb, max_lag_s=lag)
        assert abs(off) <= lag + 1e-9
    # a strong prior pulls the pick toward it when peaks are comparable
    near = estimate_time_offset(ta, tb, prior_offset_s=0.0, prior_weight=0.5)
    assert abs(near) < 0.010
    far = estimate_time_offset(ta, tb, prior_offset_s=0.25, prior_weight=5.0, max_lag_s=0.5)
    assert abs(far) > 0.1

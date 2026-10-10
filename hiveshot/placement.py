"""Camera placement evaluator and recommender (inches, field frame).

Field frame: origin at field center on the tiles, Z up, audience CELL at +Y.
Map convention in the docs: X to the right, Y up (audience CELL at the top).
Wall coordinates of +-72 in are the INSIDE face of the wall (see WALL_THICKNESS_IN).

Assumptions (documented in docs/camera_placement.md):
* Tripods stand outside the 144 in wall; the nearest a tripod head can be is
  WALL_HALF + TRIPOD_CLEARANCE_IN (6 in) from field center along X or Y.
  Candidate "radius" is the half-side of a square ring.
* GoPro Linear lens, 16:9 1080p: HFOV 86 deg. Arducam 2.3 MP, 110 deg diagonal
  lens: treated as 95 deg HFOV at 1920x1080 (lens dependent).
* Launch area: the robot launches from 12 in height, y 50-66 in (inside the
  wall, in front of the audience CELL at y=24 in), x within +-30 in of the red
  HIVE x. The brief suggested 60-110 in "away", but the wall at y=72 limits
  launch points to y<=72.
"""

from __future__ import annotations

import functools
import itertools
import math
from pathlib import Path

import cv2
import numpy as np

from . import field
from . import field_constants as C
from .synth import VirtualCamera, aim_for_cell, simulate_trajectory

WALL_HALF = C.FIELD_SIZE / 2.0          # 72
TRIPOD_CLEARANCE_IN = 6.0
# FTC perimeter wall thickness (VERIFY on the real field). Coordinates of +-72 in are the
# INSIDE face of the wall; tapes are measured from the OUTSIDE face = inside face + this.
WALL_THICKNESS_IN = 1.5
MIN_RADIUS_IN = WALL_HALF + TRIPOD_CLEARANCE_IN
HFOV_DEG = {"gopro": 86.0, "usb": 95.0}
RESOLUTION = (1920, 1080)
OCCLUSION_DIST_IN = 2.0
LAUNCH_HEIGHT_IN = C.ROBOT_LAUNCH_EXIT_HEIGHT
LAUNCH_SPEED_IPS = 230.0   # apex ~75 in; aim_for_cell returns the steep (lob) solution
EXIT_WINDOW_S = 0.2        # exit-speed camera only needs the first 0.2 s of flight
TRACK_FPS = 60.0
# Lens heights reachable with a 60 in tripod (low ones look up at the CELL tags).
HEIGHTS_IN = (12.0, 18.0, 24.0, 30.0, 36.0, 48.0, 58.0)
ANGLES_DEG = tuple(range(0, 360, 10))
WALL_STEP_IN = 12                  # extra candidates every 12 in along the audience wall
# Tag visibility: a camera "sees the tags" of the up CELL when the angle between the view ray
# to the tag row and the sticker normal is under this, all four tags are inside the image
# and the shortest projected tag edge is at least TAG_MIN_EDGE_PX.
TAG_MAX_ANGLE_DEG = 55.0
TAG_MIN_EDGE_PX = 14.0
TAG_MARGIN_PX = 60                 # tags must be this far inside the picture
REF_MARGIN_PX = 60                 # calibration reference points must be this far inside
# Printed calibration kit (tagkit.KIT_TAGS, 4 in tags on the frame top corners, facing +Y): a
# camera "reads the kit" when at least KIT_MIN_TAGS tags are under TAG_MAX_ANGLE_DEG off their
# normal, inside the picture, with the shortest projected edge >= KIT_MIN_EDGE_PX (a margin
# above bare detectability so compressed video still decodes them).
KIT_MIN_TAGS = 3
KIT_MIN_EDGE_PX = 28.0


def candidate_positions(radius_in, heights_in, angles_deg):
    """(x, y, z) on a square ring of half-side radius_in. angle 0 = +X, 90 = +Y.
    radius_in may be a scalar or a list; values below 78 in are rejected."""
    radii = [radius_in] if np.isscalar(radius_in) else list(radius_in)
    out = []
    for r, h, a in itertools.product(radii, heights_in, angles_deg):
        if r < MIN_RADIUS_IN - 1e-9:
            raise ValueError(f"radius {r} is inside the tripod limit {MIN_RADIUS_IN}")
        d = np.array([math.cos(math.radians(a)), math.sin(math.radians(a))])
        d = d / np.abs(d).max()
        # whole inches so an operator can tape-measure the spot
        out.append((float(round(r * d[0])), float(round(r * d[1])), float(h)))
    return out


def hfov_to_fx(hfov_deg: float, width: int) -> float:
    return (width / 2.0) / math.tan(math.radians(hfov_deg) / 2.0)


def camera_from_pose(pos, look_at, hfov_deg, width, height, cam_id):
    """Distortion-free pinhole with the given horizontal FOV.
    Returns (CameraIntrinsics, CameraExtrinsics)."""
    cam = VirtualCamera.look_at(cam_id, pos, look_at, width, height,
                                fx=hfov_to_fx(hfov_deg, width))
    return cam.intr, cam.extr


def _vcam(pos, look_at, hfov, cam_id="cam"):
    w, h = RESOLUTION
    return VirtualCamera(*camera_from_pose(pos, look_at, hfov, w, h, cam_id))


def sample_trajectories(dt: float = 1.0 / TRACK_FPS):
    """Six shots from the launch area, each cut where it crosses the up CELL
    opening (after that the ball is inside the HIVE)."""
    st = field.HiveState("red", "audience")
    cx = C.RED_HIVE_X
    pts = [(cx - 30, 50), (cx, 50), (cx + 30, 50), (cx - 30, 66), (cx, 66), (cx + 30, 66)]
    trajs = []
    for x, y in pts:
        lp = np.array([x, y, LAUNCH_HEIGHT_IN])
        v0 = aim_for_cell(lp, "red", "audience", st, LAUNCH_SPEED_IPS)
        tr = simulate_trajectory(lp, v0, dt, 3.0)
        end = len(tr)
        for i in range(len(tr) - 1):
            if field.segment_crosses_opening(tr[i, 1:], tr[i + 1, 1:], "red", "audience", st):
                end = i + 1
                break
        trajs.append(tr[:end])
    return trajs


def _stack(trajectories):
    return np.vstack([np.asarray(t)[:, 1:4] for t in trajectories])


def seg_seg_dist(p0, p1, q0, q1):
    """Minimum distance between segments p (N,3) and q (S,3) -> (N,S)."""
    p0 = np.atleast_2d(p0)[:, None, :]
    p1 = np.atleast_2d(p1)[:, None, :]
    q0 = np.atleast_2d(q0)[None]
    q1 = np.atleast_2d(q1)[None]
    d1, d2, r = p1 - p0, q1 - q0, p0 - q0
    a = (d1 * d1).sum(-1)
    e = (d2 * d2).sum(-1)
    f = (d2 * r).sum(-1)
    c = (d1 * r).sum(-1)
    b = (d1 * d2).sum(-1)
    den = a * e - b * b
    with np.errstate(divide="ignore", invalid="ignore"):
        s = np.clip(np.where(den > 1e-9, (b * f - c * e) / den, 0.0), 0, 1)
        t = np.where(e > 1e-12, (b * s + f) / e, 0.0)
        t_c = np.clip(t, 0, 1)
        s2 = np.clip(np.where(a > 1e-12, (b * t_c - c) / a, 0.0), 0, 1)
    s = np.where(t != t_c, s2, s)
    diff = (p0 + d1 * s[..., None]) - (q0 + d2 * t_c[..., None])
    return np.linalg.norm(diff, axis=-1)


_SEGS = None


def _frame_segments():
    global _SEGS
    if _SEGS is None:
        segs = field.hive_frame_wireframe()
        _SEGS = (np.array([s[0] for s in segs]), np.array([s[1] for s in segs]))
    return _SEGS


def occluded(cam_pos, points, margin_in: float = 4.0):
    """Per point: the ray camera->point (stopped margin_in short of the ball so
    the CELL rim the ball is entering does not count) passes within
    OCCLUSION_DIST_IN of a HIVE frame wireframe segment."""
    cam_pos = np.asarray(cam_pos, float)
    pts = np.asarray(points, float)
    v = pts - cam_pos
    length = np.linalg.norm(v, axis=1, keepdims=True)
    end = cam_pos + v * np.clip((length - margin_in) / length, 0.0, 1.0)
    q0, q1 = _frame_segments()
    d = seg_seg_dist(np.repeat(cam_pos[None], len(pts), 0), end, q0, q1)
    return (d < OCCLUSION_DIST_IN).any(axis=1)


@functools.lru_cache(maxsize=1)
def _up_tag_geometry():
    """(corners (4 tags, 4, 3), row center (3,), sticker normal (3,)) of the red audience
    CELL's tags in the audience-up state, from field.hive_tag_corners (CAD-pinned: row center
    (x_red, 13.10, 49.79), normal (0, sin30, -cos30)). Imported lazily."""
    from . import tagkit

    tags = tagkit.up_cell_tag_corners("red", "audience")
    corners = np.array([tags[k] for k in sorted(tags)])
    center = corners.reshape(-1, 3).mean(axis=0)
    c0 = corners[0]
    n = np.cross(c0[1] - c0[0], c0[0] - c0[3])       # (right) x (up), see tagkit
    n = n / np.linalg.norm(n)
    return corners, center, n


def tag_view(cam: VirtualCamera, pos) -> dict:
    """Can this camera read the up CELL's tags? angle_deg between the ray tag-row-center ->
    camera and the sticker normal, in_image (all 4 tags' corners inside with a margin),
    min_edge_px (shortest projected tag edge) and sees (all three criteria)."""
    corners, center, n = _up_tag_geometry()
    ray = np.asarray(pos, float) - center
    ray /= np.linalg.norm(ray)
    ang = math.degrees(math.acos(float(np.clip(ray @ n, -1, 1))))
    flat = corners.reshape(-1, 3)
    depth = cam.depth(flat)
    u, v = cam.project(flat)
    w, h = cam.intr.width, cam.intr.height
    m = TAG_MARGIN_PX
    inimg = bool((depth > 1.0).all() and (u >= m).all() and (u < w - m).all()
                 and (v >= m).all() and (v < h - m).all())
    uv = np.c_[u, v].reshape(len(corners), 4, 2)
    edges = np.linalg.norm(uv - np.roll(uv, -1, axis=1), axis=2)
    edge = float(edges.min())
    return {"angle_deg": ang, "in_image": inimg, "min_edge_px": edge,
            "sees": bool(ang < TAG_MAX_ANGLE_DEG and inimg and edge >= TAG_MIN_EDGE_PX)}


def kit_view(cam: VirtualCamera, pos) -> dict:
    """Readability of the printed kit tags from this camera: per-tag
    {id: {"angle_deg", "min_edge_px", "in_image", "ok"}} and n_ok / ok (n_ok >= KIT_MIN_TAGS)."""
    from . import tagkit

    out = {}
    w, h = cam.intr.width, cam.intr.height
    m = TAG_MARGIN_PX
    for t in tagkit.KIT_TAGS:
        c = tagkit.tag_corners_xyz(t)
        n = np.cross(c[1] - c[0], c[0] - c[3])
        n /= np.linalg.norm(n)
        ray = np.asarray(pos, float) - c.mean(axis=0)
        ray /= np.linalg.norm(ray)
        ang = math.degrees(math.acos(float(np.clip(ray @ n, -1, 1))))
        u, v = cam.project(c)
        uv = np.c_[u, v]
        edge = float(np.linalg.norm(uv - np.roll(uv, -1, axis=0), axis=1).min())
        inimg = bool((cam.depth(c) > 1.0).all() and (u >= m).all() and (u < w - m).all()
                     and (v >= m).all() and (v < h - m).all())
        out[t.id] = {"angle_deg": ang, "min_edge_px": edge, "in_image": inimg,
                     "ok": bool(ang < TAG_MAX_ANGLE_DEG and inimg and edge >= KIT_MIN_EDGE_PX)}
    n_ok = sum(1 for d in out.values() if d["ok"])
    return {"tags": out, "n_ok": n_ok, "ok": n_ok >= KIT_MIN_TAGS}


def refs_in_view(cam: VirtualCamera) -> bool:
    """All 8 calibration reference points (calib_targets) project inside the image."""
    from . import calib_targets

    xyz = np.array([p for _, p in calib_targets.field_reference_points()])
    depth = cam.depth(xyz)
    u, v = cam.project(xyz)
    m = REF_MARGIN_PX
    return bool((depth > 1.0).all() and (u >= m).all() and (u <= cam.intr.width - m).all()
                and (v >= m).all() and (v <= cam.intr.height - m).all())


def _cam_pos(cam: VirtualCamera):
    return -cam.R.T @ cam.tvec.ravel()


def _per_camera(cam: VirtualCamera, pos, pts):
    depth = cam.depth(pts)
    u, v = cam.project(pts)
    inimg = ((depth > 1.0) & (u >= 0) & (u < cam.intr.width)
             & (v >= 0) & (v < cam.intr.height))
    rpx = cam.intr.fx * (C.POLLEN_DIAMETER / 2) / np.maximum(depth, 1.0)
    return {"in": inimg, "r": rpx, "occ": occluded(pos, pts)}


def _angle_deg(pa, pb, pts):
    ra = np.asarray(pa, float) - pts
    rb = np.asarray(pb, float) - pts
    cosang = (ra * rb).sum(1) / (np.linalg.norm(ra, axis=1) * np.linalg.norm(rb, axis=1))
    return np.degrees(np.arccos(np.clip(cosang, -1, 1)))


def _angle_quality(a: float) -> float:
    if a < 60:
        return max(0.0, 1.0 - (60 - a) / 30.0)
    if a > 120:
        return max(0.0, 1.0 - (a - 120) / 30.0)
    return 1.0


def _combine(pa, pb, da, db, pts):
    both = da["in"] & db["in"]
    n = len(pts)
    frac = float(both.mean())
    ang = _angle_deg(pa, pb, pts)
    mean_ang = float(ang[both].mean()) if both.any() else 0.0
    mean_r = float(np.minimum(da["r"], db["r"])[both].mean()) if both.any() else 0.0
    occ_frac = float(((da["occ"] | db["occ"]) & both).sum() / n)
    score = (frac * _angle_quality(mean_ang) * min(1.0, mean_r / 4.0) * (1.0 - occ_frac)
             * (1.0 if frac >= 0.9 else 0.5))
    return {"score": float(score), "frac_in_both": frac, "mean_angle_deg": mean_ang,
            "mean_radius_px": mean_r, "occluded_frac": occ_frac, "n_points": n}


def score_pair(camA, camB, trajectories) -> dict:
    """camA/camB: VirtualCamera. trajectories: list of (N,4) [t,x,y,z] arrays.
    Returns score plus frac_in_both, mean_angle_deg, mean_radius_px, occluded_frac."""
    pts = _stack(trajectories)
    pa, pb = _cam_pos(camA), _cam_pos(camB)
    return _combine(pa, pb, _per_camera(camA, pa, pts), _per_camera(camB, pb, pts), pts)


def _aim_point(trajectories):
    c = _stack(trajectories).mean(axis=0)
    return tuple(float(round(v)) for v in c)


@functools.lru_cache(maxsize=4)
def recommend(option: str = "gopro") -> dict:
    """Grid-search the best A/B pair and a third (exit-speed) camera.
    Result: {"option", "hfov_deg", "pair_score": {...},
             "cameras": {"A": {...}, "B": {...}, "C": {...}}}, each camera
    having pos (x,y,z), look_at, height_in, hfov_deg."""
    if option not in HFOV_DEG:
        raise ValueError("option must be 'gopro' or 'usb'")
    hfov = HFOV_DEG[option]
    trajs = sample_trajectories()
    pts = _stack(trajs)
    aim = _aim_point(trajs)
    pa0, pb0 = _joint_pair()
    best = _eval_pair(_entry(pa0, aim, hfov, pts), _entry(pb0, aim, hfov, pts), pts)
    # Re-aim each camera to the middle of the aim range that keeps the tags and calibration
    # points in view, so a few degrees of aiming error at the field do not lose them.
    aims = {pa0: _center_aim(pa0, aim, hfov), pb0: _center_aim(pb0, aim, hfov)}
    cand = _eval_pair(_entry(pa0, aims[pa0], hfov, pts), _entry(pb0, aims[pb0], hfov, pts), pts)
    if cand[0][0] >= best[0][0]:
        best = cand
    else:
        aims = {pa0: aim, pb0: aim}
    key, sc, (pa, ta), (pb, tb) = best
    # A is the camera on the -X side (left of the map), B on the +X side, for stable labels.
    if pa[0] > pb[0]:
        pa, pb, ta, tb = pb, pa, tb, ta
    sc = dict(sc, tags_both=bool(ta["sees"] and tb["sees"]), kit_both=bool(key[0][1]),
              refs_in_both=bool(key[0][3]), tier=key[0])
    return {
        "option": option, "hfov_deg": hfov, "resolution": RESOLUTION, "pair_score": sc,
        "tags": {"A": ta, "B": tb},
        "cameras": {
            "A": {"pos": pa, "look_at": aims[pa], "height_in": pa[2], "hfov_deg": hfov},
            "B": {"pos": pb, "look_at": aims[pb], "height_in": pb[2], "hfov_deg": hfov},
            "C": _recommend_third(hfov, trajs),
        },
    }


def _rotated_aim(pos, aim, dyaw_deg, dpitch_deg):
    """Aim point (whole inches) after turning the optical axis by dyaw / dpitch degrees."""
    d = np.asarray(aim, float) - np.asarray(pos, float)
    dist = float(np.linalg.norm(d))
    yaw = math.degrees(math.atan2(d[1], d[0])) + dyaw_deg
    pitch = math.degrees(math.atan2(d[2], math.hypot(d[0], d[1]))) + dpitch_deg
    v = np.array([math.cos(math.radians(pitch)) * math.cos(math.radians(yaw)),
                  math.cos(math.radians(pitch)) * math.sin(math.radians(yaw)),
                  math.sin(math.radians(pitch))])
    return tuple(float(round(c)) for c in np.asarray(pos, float) + dist * v)


def _aim_ok(pos, look, hfov) -> bool:
    vc = _vcam(pos, look, hfov)
    return bool(tag_view(vc, pos)["sees"] and kit_view(vc, pos)["ok"] and refs_in_view(vc))


def _center_aim(pos, aim, hfov, span=8, step=1.0):
    """Aim point for the camera at `pos` in the middle of the (yaw, pitch) offsets within
    +-span deg for which `_aim_ok` holds (largest distance from the failing region); the
    nominal aim if even that fails."""
    n = int(span / step)
    ok = np.zeros((2 * n + 1, 2 * n + 1), np.uint8)
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            if _aim_ok(pos, _rotated_aim(pos, aim, i * step, j * step), hfov):
                ok[i + n, j + n] = 1
    if not ok[n, n]:
        return aim
    dist = cv2.distanceTransform(np.pad(ok, 1), cv2.DIST_L2, 3)[1:-1, 1:-1]
    i, j = np.unravel_index(int(np.argmax(dist)), dist.shape)
    return _rotated_aim(pos, aim, (i - n) * step, (j - n) * step)


@functools.lru_cache(maxsize=1)
def _joint_pair():
    """Best (pos A, pos B) over ALL lens options at once, so one set of tape marks serves
    Option A and Option B: tiers compare as the worse of the two options, value as the mean."""
    trajs = sample_trajectories()
    pts = _stack(trajs)
    aim = _aim_point(trajs)
    caches = [[_entry(p, aim, h, pts) for p in _candidates()] for h in HFOV_DEG.values()]
    best = None
    for idx in itertools.combinations(range(len(caches[0])), 2):
        if math.dist(caches[0][idx[0]][0][:2], caches[0][idx[1]][0][:2]) < 24:
            continue
        evals = [_eval_pair(c[idx[0]], c[idx[1]], pts) for c in caches]
        key = (min(e[0][0] for e in evals), sum(e[0][1] for e in evals) / len(evals))
        if best is None or key[0] > best[0][0] or (
                key[0] == best[0][0] and key[1] > best[0][1] + 1e-9):
            best = (key, caches[0][idx[0]][0], caches[0][idx[1]][0])
    return best[1], best[2]


def _entry(p, aim, hfov, pts):
    """Per-candidate data: (pos, per-camera sample-point data, tag view incl. kit, refs ok)."""
    vc = _vcam(p, aim, hfov)
    tv = tag_view(vc, p)
    tv["kit"] = kit_view(vc, p)
    return (p, _per_camera(vc, p, pts), tv, refs_in_view(vc))


def _eval_pair(ea, eb, pts):
    """((tier, value), score dict, (pos A, tags A), (pos B, tags B)) for a candidate pair.
    tier = (arc and triangulation ok, both cameras read the kit, both read the CELL tags,
    all 8 reference points in view in both); tuples compare lexicographically."""
    (pa, da, ta, ra), (pb, db, tb, rb) = ea, eb
    sc = _combine(pa, pb, da, db, pts)
    arc_ok = sc["frac_in_both"] >= 0.9 and 60.0 <= sc["mean_angle_deg"] <= 120.0
    tier = (arc_ok, ta["kit"]["ok"] and tb["kit"]["ok"], ta["sees"] and tb["sees"], ra and rb)
    tq = 0.5 * (math.cos(math.radians(ta["angle_deg"])) + math.cos(math.radians(tb["angle_deg"])))
    value = sc["score"] * (0.5 + 0.5 * max(tq, 0.0))
    return ((tier, value), sc, (pa, ta), (pb, tb))


def _candidates():
    """Ring candidates plus positions every WALL_STEP_IN along the audience (+Y) wall."""
    out = list(candidate_positions(MIN_RADIUS_IN, HEIGHTS_IN, ANGLES_DEG))
    for h in HEIGHTS_IN:
        for x in range(-int(WALL_HALF), int(WALL_HALF) + 1, WALL_STEP_IN):
            out.append((float(x), MIN_RADIUS_IN, float(h)))
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def _recommend_third(hfov, trajs):
    """Exit-speed camera behind the robot (audience side, +Y, outside the
    wall), near the launch line, looking along it toward the HIVE. Scored on
    the first EXIT_WINDOW_S of each flight, where exit speed is measured."""
    n_early = int(EXIT_WINDOW_S * TRACK_FPS)
    pts = _stack([t[:n_early] for t in trajs])
    cx = C.RED_HIVE_X
    best = None
    for x, y, h in itertools.product((round(cx) - 12, round(cx), round(cx) + 12), (MIN_RADIUS_IN,),
                                     (48.0, 58.0)):
        pos = (x, y, h)
        for ay, az in itertools.product((20.0, 35.0, 50.0), (30.0, 45.0, 60.0)):
            look = (cx, ay, az)
            d = _per_camera(_vcam(pos, look, hfov), pos, pts)
            frac = float(d["in"].mean())
            occ = float((d["occ"] & d["in"]).sum() / len(pts))
            r = float(d["r"][d["in"]].mean()) if d["in"].any() else 0.0
            score = frac * (1 - occ) * min(1.0, r / 4.0)
            if best is None or score > best["score"] + 1e-9:
                best = {"pos": pos, "look_at": look, "height_in": h, "hfov_deg": hfov,
                        "score": score, "frac_in_view": frac, "occluded_frac": occ,
                        "mean_radius_px": r}
    return best


def operator_measurements(pos, wall_thickness_in: float = WALL_THICKNESS_IN) -> dict:
    """Tape-measure numbers: offset from field center, and from the nearest
    wall corner (distance out from the wall, and along the wall).

    out_from_wall_in / along_wall_from_corner_in are measured from the INSIDE face of the
    wall (the +-72 in plane). out_from_outer_face_in / along_from_outer_edge_in are the
    same spots measured from the OUTSIDE face / outer edge of a wall of the given thickness
    (what a person standing outside the field can reach with a tape)."""
    x, y, z = pos
    if abs(y) >= abs(x):
        wall, out, along = ("+Y" if y > 0 else "-Y"), abs(y) - WALL_HALF, WALL_HALF - abs(x)
    else:
        wall, out, along = ("+X" if x > 0 else "-X"), abs(x) - WALL_HALF, WALL_HALF - abs(y)
    corner = (math.copysign(WALL_HALF, x), math.copysign(WALL_HALF, y))
    return {"wall": wall, "out_from_wall_in": out, "along_wall_from_corner_in": along,
            "out_from_outer_face_in": out - wall_thickness_in,
            "along_from_outer_edge_in": along + wall_thickness_in,
            "corner": corner, "from_center_in": (x, y), "height_in": z}


def aim_angles(cam) -> tuple[float, float]:
    """(yaw_deg, pitch_deg) of the optical axis of a recommend() camera dict.
    Yaw is the field-frame bearing in degrees from +X toward +Y, in [0, 360); pitch is
    degrees above (+) or below (-) the horizontal."""
    d = [cam["look_at"][i] - cam["pos"][i] for i in range(3)]
    yaw = math.degrees(math.atan2(d[1], d[0])) % 360.0
    pitch = math.degrees(math.atan2(d[2], math.hypot(d[0], d[1])))
    return yaw, pitch


def pixel_numbers(option: str) -> dict:
    """Ball diameter in pixels (min/mean/max over in-image sample points)."""
    rec = recommend(option)
    pts = _stack(sample_trajectories())
    out = {}
    for k, c in rec["cameras"].items():
        cam = _vcam(c["pos"], c["look_at"], c["hfov_deg"])
        m = _per_camera(cam, c["pos"], pts)["in"]
        dia = 2 * cam.intr.fx * (C.POLLEN_DIAMETER / 2) / cam.depth(pts[m])
        out[k] = {"min": float(dia.min()), "mean": float(dia.mean()), "max": float(dia.max()),
                  "fx": float(cam.intr.fx)}
    return out


# ------------------------------------------------------------------ map
S = 1600
SCALE = S / 260.0                      # px per inch; map spans +-130 in
ROLES = {"A": "primary", "B": "primary", "C": "exit speed"}
COLORS = {"A": (200, 90, 20), "B": (30, 140, 30), "C": (150, 40, 150)}  # BGR
LAUNCH_RECT = (C.RED_HIVE_X - 36, 44, C.RED_HIVE_X + 36, 70)   # x0, y0, x1, y1


def _m(x, y):
    return (S / 2 + x * SCALE, S / 2 - y * SCALE)


def _hex(bgr):
    return "#%02x%02x%02x" % (bgr[2], bgr[1], bgr[0])


def _cone_pts(cam, length=100.0):
    """Floor-plan view cone: apex plus the two horizontal FOV edge endpoints."""
    pos = np.array(cam["pos"][:2])
    d = np.array(cam["look_at"][:2]) - pos
    base = math.atan2(d[1], d[0])
    half = math.radians(cam["hfov_deg"] / 2)
    pts = [(pos[0], pos[1])]
    for s in (-1, 1):
        pts.append((pos[0] + length * math.cos(base + s * half),
                    pos[1] + length * math.sin(base + s * half)))
    return pts


def label_lines(name, cam):
    """Three legend lines for a camera (operator tape-measure numbers)."""
    m = operator_measurements(cam["pos"])
    x, y, z = cam["pos"]
    lx, ly, lz = cam["look_at"]
    yaw, pitch = aim_angles(cam)
    if name in ("A", "B"):
        tv = tag_view(_vcam(cam["pos"], cam["look_at"], cam["hfov_deg"]), cam["pos"])
        tail = (f"HIVE tags {tv['angle_deg']:.0f} deg off normal "
                f"({'readable' if tv['sees'] else 'NOT readable'}, limit {TAG_MAX_ANGLE_DEG:.0f})")
    else:
        tail = f"HFOV {cam['hfov_deg']:.0f}"
    return [
        f"CAM {name} - {ROLES[name]}: x={x:+.0f} y={y:+.0f} in from center, "
        f"lens height {z:.0f} in",
        f"{m['out_from_wall_in']:.0f} in out from the {m['wall']} wall's INSIDE face, "
        f"{m['along_wall_from_corner_in']:.0f} in along the wall from corner "
        f"({m['corner'][0]:+.0f},{m['corner'][1]:+.0f})",
        f"aim yaw {yaw:.0f} deg (from +X toward +Y), pitch {pitch:+.0f} deg; "
        f"aim point ({lx:+.0f},{ly:+.0f},{lz:.0f}); " + tail,
    ]


LEGEND_Y0 = 1300
LEGEND_DY = 95
TAG_OFFSET = {"A": (-28, 8, "end"), "B": (28, 8, "start"), "C": (0, -30, "middle")}


def write_map(option: str, svg_path, png_path) -> None:
    """Write the top-down map as SVG and as a 1600x1600 PNG (drawn with cv2),
    both from recommend(option)."""
    rec = recommend(option)
    Path(svg_path).write_text(_svg(option, rec), encoding="utf-8")
    cv2.imwrite(str(png_path), _png(option, rec))


def _svg(option, rec):
    h = WALL_HALF
    fw, fd = C.FRAME_WIDTH_X / 2, C.FRAME_DEPTH_Y / 2
    cell, _ = field.cell_opening_plane("red", "audience", field.HiveState("red", "audience"))
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{S}" height="{S}" '
         f'viewBox="0 0 {S} {S}" font-family="Arial, sans-serif">',
         f'<rect width="{S}" height="{S}" fill="#ffffff"/>']
    x0, y0 = _m(-h, h)
    o.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{2*h*SCALE:.1f}" height="{2*h*SCALE:.1f}" '
             f'fill="#e9e9e9" stroke="#000" stroke-width="6"/>')
    for i in range(-3, 4):
        for (a, b) in (((i * 24, -h), (i * 24, h)), ((-h, i * 24), (h, i * 24))):
            (ax, ay), (bx, by) = _m(*a), _m(*b)
            o.append(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" '
                     f'stroke="#b0b0b0" stroke-width="2"/>')
    lx, ly = _m(LAUNCH_RECT[0], LAUNCH_RECT[3])
    o.append(f'<rect x="{lx:.1f}" y="{ly:.1f}" '
             f'width="{(LAUNCH_RECT[2]-LAUNCH_RECT[0])*SCALE:.1f}" '
             f'height="{(LAUNCH_RECT[3]-LAUNCH_RECT[1])*SCALE:.1f}" fill="#ffe9a8" '
             f'fill-opacity="0.7" stroke="#c08000" stroke-width="3" stroke-dasharray="14 8"/>')
    o.append(f'<text x="{lx+10:.1f}" y="{ly+30:.1f}" font-size="26" fill="#805000">'
             f'LAUNCH AREA (y 44..70)</text>')
    fx0, fy0 = _m(-fw, fd)
    o.append(f'<rect x="{fx0:.1f}" y="{fy0:.1f}" width="{2*fw*SCALE:.1f}" '
             f'height="{2*fd*SCALE:.1f}" fill="#999999" fill-opacity="0.5" stroke="#333" '
             f'stroke-width="4"/>')
    for label, col, hx in (("RED beam", "#d02020", C.RED_HIVE_X),
                           ("BLUE beam", "#2040d0", C.BLUE_HIVE_X)):
        (ax, ay), (bx, by) = _m(hx, -field.OPENING_CENTER_ABS_Y), _m(hx, field.OPENING_CENTER_ABS_Y)
        o.append(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" '
                 f'stroke="{col}" stroke-width="14"/>')
        tx, ty = _m(hx, -fd - 6)
        o.append(f'<text x="{tx:.1f}" y="{ty+24:.1f}" font-size="24" fill="{col}" '
                 f'text-anchor="middle">{label}</text>')
    cx, cy = _m(cell[0], cell[1])
    o.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="16" fill="none" stroke="#000" '
             f'stroke-width="5"/>')
    o.append(f'<text x="{cx+24:.1f}" y="{cy-20:.1f}" font-size="26">'
             f'UP CELL (red, audience, +Y)</text>')
    for k in ("A", "B", "C"):
        cam = rec["cameras"][k]
        col = _hex(COLORS[k])
        pp = " ".join(f"{_m(*p)[0]:.1f},{_m(*p)[1]:.1f}" for p in _cone_pts(cam))
        px, py = _m(*cam["pos"][:2])
        ax, ay = _m(*cam["look_at"][:2])
        o.append(f'<polygon points="{pp}" fill="{col}" fill-opacity="0.12" stroke="{col}" '
                 f'stroke-width="3" stroke-dasharray="10 6"/>')
        o.append(f'<line x1="{px:.1f}" y1="{py:.1f}" x2="{ax:.1f}" y2="{ay:.1f}" '
                 f'stroke="{col}" stroke-width="4"/>')
        o.append(f'<circle cx="{ax:.1f}" cy="{ay:.1f}" r="8" fill="{col}"/>')
        o.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="18" fill="{col}"/>')
        dx, dy, anchor = TAG_OFFSET[k]
        o.append(f'<text x="{px+dx:.1f}" y="{py+dy:.1f}" font-size="28" font-weight="bold" '
                 f'fill="{col}" text-anchor="{anchor}">CAM {k}</text>')
        for i, txt in enumerate(label_lines(k, cam)):
            o.append(f'<text x="30" y="{LEGEND_Y0 + LEGEND_DY*("ABC".index(k)) + i*30}" '
                     f'font-size="{24 if i == 0 else 21}" fill="{col}" '
                     f'font-weight="{"bold" if i == 0 else "normal"}">{txt}</text>')
    o.append(f'<text x="30" y="50" font-size="34" font-weight="bold">HIVE Shot Tracker camera '
             f'map - option {option.upper()} (HFOV {rec["hfov_deg"]:.0f} deg)</text>')
    o.append('<text x="30" y="88" font-size="24">Top-down. X right, Y up (audience CELL at top). '
             'Inches from field center. Tiles 24 in. Wall at +-72 = INSIDE face.</text>')
    o.append('<text x="30" y="122" font-size="24">Yaw = bearing from +X toward +Y (0 = right, '
             '90 = up, 180 = left, 270 = down). Pitch + = up.</text>')
    o.append('</svg>')
    return "\n".join(o)


def _png(option, rec):
    h = WALL_HALF
    fw, fd = C.FRAME_WIDTH_X / 2, C.FRAME_DEPTH_Y / 2
    cell, _ = field.cell_opening_plane("red", "audience", field.HiveState("red", "audience"))
    font = cv2.FONT_HERSHEY_SIMPLEX
    img = np.full((S, S, 3), 255, np.uint8)

    def P(x, y):
        a, b = _m(x, y)
        return int(round(a)), int(round(b))

    def blend(fill_fn, alpha):
        nonlocal img
        ov = img.copy()
        fill_fn(ov)
        img = cv2.addWeighted(ov, alpha, img, 1 - alpha, 0)

    cv2.rectangle(img, P(-h, h), P(h, -h), (233, 233, 233), -1)
    for i in range(-3, 4):
        cv2.line(img, P(i * 24, -h), P(i * 24, h), (176, 176, 176), 2)
        cv2.line(img, P(-h, i * 24), P(h, i * 24), (176, 176, 176), 2)
    cv2.rectangle(img, P(-h, h), P(h, -h), (0, 0, 0), 6)
    lr = LAUNCH_RECT
    blend(lambda o: cv2.rectangle(o, P(lr[0], lr[3]), P(lr[2], lr[1]), (168, 233, 255), -1), 0.7)
    cv2.rectangle(img, P(lr[0], lr[3]), P(lr[2], lr[1]), (0, 128, 192), 3)
    lx, ly = P(lr[0], lr[3])
    cv2.putText(img, "LAUNCH AREA (y 44..70)", (lx + 10, ly + 30), font, 0.7, (0, 80, 128), 2,
                cv2.LINE_AA)
    blend(lambda o: cv2.rectangle(o, P(-fw, fd), P(fw, -fd), (153, 153, 153), -1), 0.5)
    cv2.rectangle(img, P(-fw, fd), P(fw, -fd), (51, 51, 51), 4)
    for label, col, hx in (("RED beam", (32, 32, 208), C.RED_HIVE_X),
                           ("BLUE beam", (208, 64, 32), C.BLUE_HIVE_X)):
        cv2.line(img, P(hx, -field.OPENING_CENTER_ABS_Y), P(hx, field.OPENING_CENTER_ABS_Y), col, 14)
        tx, ty = P(hx, -fd - 6)
        w = cv2.getTextSize(label, font, 0.6, 2)[0][0]
        cv2.putText(img, label, (tx - w // 2, ty + 24), font, 0.6, col, 2, cv2.LINE_AA)
    cx, cy = P(cell[0], cell[1])
    cv2.circle(img, (cx, cy), 16, (0, 0, 0), 5)
    cv2.putText(img, "UP CELL (red, audience, +Y)", (cx + 24, cy - 20), font, 0.7, (0, 0, 0), 2,
                cv2.LINE_AA)
    for k in ("A", "B", "C"):
        cam = rec["cameras"][k]
        col = COLORS[k]
        cone = [P(*p) for p in _cone_pts(cam)]
        blend(lambda o, cone=cone, col=col: cv2.fillPoly(o, [np.array(cone, np.int32)], col),
              0.12)
        cv2.line(img, cone[0], cone[1], col, 3, cv2.LINE_AA)
        cv2.line(img, cone[0], cone[2], col, 3, cv2.LINE_AA)
        p0, a0 = P(*cam["pos"][:2]), P(*cam["look_at"][:2])
        cv2.line(img, p0, a0, col, 4, cv2.LINE_AA)
        cv2.circle(img, a0, 8, col, -1)
        cv2.circle(img, p0, 18, col, -1)
        dx, dy, anchor = TAG_OFFSET[k]
        w = cv2.getTextSize(f"CAM {k}", font, 0.9, 2)[0][0]
        x = p0[0] + dx - (w if anchor == "end" else w // 2 if anchor == "middle" else 0)
        cv2.putText(img, f"CAM {k}", (x, p0[1] + dy), font, 0.9, col, 2, cv2.LINE_AA)
        for i, txt in enumerate(label_lines(k, cam)):
            scale, thick = (0.72, 2) if i == 0 else (0.62, 1)
            cv2.putText(img, txt, (30, LEGEND_Y0 + LEGEND_DY * "ABC".index(k) + i * 30), font,
                        scale, col, thick, cv2.LINE_AA)
    cv2.putText(img, f"HIVE Shot Tracker camera map - option {option.upper()} "
                f"(HFOV {rec['hfov_deg']:.0f} deg)", (30, 50), font, 0.95, (0, 0, 0), 2,
                cv2.LINE_AA)
    cv2.putText(img, "Top-down. X right, Y up (audience CELL at top). Inches from field "
                "center. Tiles 24 in. Wall at +-72 = INSIDE face.", (30, 88), font, 0.6,
                (0, 0, 0), 1, cv2.LINE_AA)
    cv2.putText(img, "Yaw = bearing from +X toward +Y (0 = right, 90 = up, 180 = left, "
                "270 = down). Pitch + = up.", (30, 122), font, 0.6, (0, 0, 0), 1, cv2.LINE_AA)
    return img

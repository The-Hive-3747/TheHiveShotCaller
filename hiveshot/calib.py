"""Camera calibration: intrinsics, extrinsics, triangulation, persistence.

Conventions: field coordinates in inches (see hiveshot.field_constants).
Extrinsics map field -> camera: X_cam = R @ X_field + t.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Sequence

import cv2
import numpy as np

from hiveshot import field_constants as fc
from hiveshot.models import CameraExtrinsics, CameraIntrinsics

MIN_CALIB_FRAMES = 8


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def camera_matrix(intr: CameraIntrinsics) -> np.ndarray:
    return np.array(
        [[intr.fx, 0.0, intr.cx], [0.0, intr.fy, intr.cy], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )


def dist_coeffs(intr: CameraIntrinsics) -> np.ndarray:
    d = np.asarray(intr.dist, dtype=np.float64).reshape(-1)
    return d if d.size else np.zeros(5)


def _rt(ext: CameraExtrinsics) -> tuple[np.ndarray, np.ndarray]:
    rvec = np.asarray(ext.rvec, dtype=np.float64).reshape(3, 1)
    R, _ = cv2.Rodrigues(rvec)
    return R, np.asarray(ext.tvec, dtype=np.float64).reshape(3)


def checkerboard_object_points(pattern: tuple[int, int], square_in: float) -> np.ndarray:
    """(cols*rows, 3) inner-corner coordinates on Z=0, in inches."""
    cols, rows = pattern
    objp = np.zeros((cols * rows, 3), np.float64)
    objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2) * square_in
    return objp


# --------------------------------------------------------------------------
# Intrinsics
# --------------------------------------------------------------------------
def calibrate_intrinsics_from_corners(
    object_points_list: Sequence[np.ndarray],
    image_points_list: Sequence[np.ndarray],
    image_size: tuple[int, int],
    cam_id: str,
) -> CameraIntrinsics:
    """Run cv2.calibrateCamera. image_size is (width, height)."""
    if len(object_points_list) < MIN_CALIB_FRAMES:
        raise ValueError(
            f"Need at least {MIN_CALIB_FRAMES} usable checkerboard frames for "
            f"camera '{cam_id}', got {len(object_points_list)}."
        )
    obj = [np.asarray(o, np.float32).reshape(-1, 1, 3) for o in object_points_list]
    img = [np.asarray(p, np.float32).reshape(-1, 1, 2) for p in image_points_list]
    w, h = int(image_size[0]), int(image_size[1])
    rms, K, dist, _, _ = cv2.calibrateCamera(obj, img, (w, h), None, None)
    dist = np.asarray(dist).reshape(-1)
    return CameraIntrinsics(
        cam_id=cam_id,
        width=w,
        height=h,
        fx=float(K[0, 0]),
        fy=float(K[1, 1]),
        cx=float(K[0, 2]),
        cy=float(K[1, 2]),
        dist=tuple(float(x) for x in dist),
        reprojection_rmse_px=float(rms),
    )


def calibrate_intrinsics(
    frames: list[np.ndarray],
    pattern: tuple[int, int] = (9, 6),
    square_in: float = 1.0,
    cam_id: str = "cam",
) -> CameraIntrinsics:
    """Detect inner corners (sub-pixel) in each frame and calibrate.

    Frames where the pattern is not found are skipped. Raises ValueError if
    fewer than 8 frames are usable.
    """
    objp = checkerboard_object_points(pattern, square_in)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.001)
    objs: list[np.ndarray] = []
    imgs: list[np.ndarray] = []
    size: Optional[tuple[int, int]] = None
    for fr in frames:
        gray = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY) if fr.ndim == 3 else fr
        if size is None:
            size = (gray.shape[1], gray.shape[0])
        elif size != (gray.shape[1], gray.shape[0]):
            continue
        ok, corners = cv2.findChessboardCorners(gray, pattern)
        if not ok:
            continue
        corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), crit)
        objs.append(objp)
        imgs.append(corners.reshape(-1, 2))
    if size is None or len(objs) < MIN_CALIB_FRAMES:
        raise ValueError(
            f"Only {len(objs)} of {len(frames)} frames had a detectable "
            f"{pattern[0]}x{pattern[1]} checkerboard for camera '{cam_id}'; "
            f"need at least {MIN_CALIB_FRAMES}. Hold the board flat, fully "
            "visible, at varied angles and distances."
        )
    return calibrate_intrinsics_from_corners(objs, imgs, size, cam_id)


# --------------------------------------------------------------------------
# Projection / undistortion
# --------------------------------------------------------------------------
def undistort_points(intr: CameraIntrinsics, pts: np.ndarray, normalized: bool = False) -> np.ndarray:
    """Undistort (N,2) pixel points. Returns pixel coords of an ideal pinhole
    camera with the same K, or normalized coords (x/z, y/z) if normalized=True."""
    p = np.asarray(pts, np.float64).reshape(-1, 1, 2)
    K = camera_matrix(intr)
    out = cv2.undistortPoints(p, K, dist_coeffs(intr), P=None if normalized else K)
    return out.reshape(-1, 2)


def project(intr: CameraIntrinsics, ext: CameraExtrinsics, xyz: np.ndarray) -> np.ndarray:
    """Project field points (N,3) to distorted pixel coords (N,2)."""
    pts = np.asarray(xyz, np.float64).reshape(-1, 1, 3)
    rvec = np.asarray(ext.rvec, np.float64).reshape(3, 1)
    tvec = np.asarray(ext.tvec, np.float64).reshape(3, 1)
    uv, _ = cv2.projectPoints(pts, rvec, tvec, camera_matrix(intr), dist_coeffs(intr))
    return uv.reshape(-1, 2)


# --------------------------------------------------------------------------
# Extrinsics
# --------------------------------------------------------------------------
def _mean_depth(ext: CameraExtrinsics, field_points: np.ndarray) -> float:
    R, t = _rt(ext)
    return float(np.mean((field_points @ R.T + t)[:, 2]))


def reprojection_report(
    intr: CameraIntrinsics,
    ext: CameraExtrinsics,
    image_points: np.ndarray,
    field_points: np.ndarray,
) -> dict:
    """Per-point reprojection error (px) and RMSE, plus RMSE in inches.

    rmse_in = rmse_px * mean_depth_in / mean(fx, fy), i.e. the lateral size of
    the pixel error at the mean point depth.
    """
    img = np.asarray(image_points, np.float64).reshape(-1, 2)
    fld = np.asarray(field_points, np.float64).reshape(-1, 3)
    err = np.linalg.norm(project(intr, ext, fld) - img, axis=1)
    rmse_px = float(np.sqrt(np.mean(err**2)))
    depth = _mean_depth(ext, fld)
    rmse_in = rmse_px * depth / (0.5 * (intr.fx + intr.fy))
    return {
        "per_point_px": [float(e) for e in err],
        "rmse_px": rmse_px,
        "max_px": float(err.max()),
        "mean_depth_in": depth,
        "rmse_in": float(rmse_in),
    }


def solve_extrinsics_from_points(
    intr: CameraIntrinsics,
    image_points: np.ndarray,
    field_points: np.ndarray,
    cam_id: str,
    ransac_thresh_px: float = 4.0,
    use_ransac: bool = True,
) -> CameraExtrinsics:
    """Pose of the camera from 2D-3D correspondences via cv2.solvePnP.

    N < 4: error. 4 <= N < 6: SQPNP. N >= 6: RANSAC (SQPNP) to reject bad
    clicks, then ITERATIVE refinement on inliers (use_ransac=False skips the outlier
    rejection and refines all points: for detector output such as tag corners, where
    a few tightly clustered planar points make RANSAC subsets degenerate). rmse_in is the reprojection
    RMSE in px converted to inches at the mean point depth:
        rmse_in = rmse_px * mean_depth / ((fx + fy) / 2).
    """
    img = np.asarray(image_points, np.float64).reshape(-1, 2)
    fld = np.asarray(field_points, np.float64).reshape(-1, 3)
    n = len(img)
    if n != len(fld):
        raise ValueError("image_points and field_points must have the same length")
    if n < 4:
        raise ValueError(f"Need at least 4 point correspondences, got {n}")
    K, D = camera_matrix(intr), dist_coeffs(intr)
    if n >= 6 and use_ransac:
        ok, rvec, tvec, inl = cv2.solvePnPRansac(
            fld, img, K, D, flags=cv2.SOLVEPNP_SQPNP,
            reprojectionError=ransac_thresh_px, confidence=0.999, iterationsCount=200,
        )
        if not ok or inl is None or len(inl) < 4:
            raise ValueError("PnP RANSAC failed: too few consistent points")
        idx = inl.reshape(-1)
        ok, rvec, tvec = cv2.solvePnP(
            fld[idx], img[idx], K, D, rvec, tvec, useExtrinsicGuess=True,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
    else:
        ok, rvec, tvec = cv2.solvePnP(fld, img, K, D, flags=cv2.SOLVEPNP_SQPNP)
        if ok and n >= 6:
            ok, rvec, tvec = cv2.solvePnP(fld, img, K, D, rvec, tvec, useExtrinsicGuess=True,
                                          flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok:
        raise ValueError("solvePnP failed")
    ext = CameraExtrinsics(
        cam_id=cam_id,
        rvec=tuple(float(x) for x in rvec.reshape(3)),
        tvec=tuple(float(x) for x in tvec.reshape(3)),
    )
    rep = reprojection_report(intr, ext, img, fld)
    ext.rmse_in = rep["rmse_in"]
    return ext


# --------------------------------------------------------------------------
# AprilTags
# --------------------------------------------------------------------------
def detect_apriltags(image: np.ndarray, intr: Optional[CameraIntrinsics] = None) -> list[dict]:
    """Detect 36h11 AprilTags. Returns [{'id': int, 'corners': (4,2)}].

    Corner order is the ArUco order (top-left, top-right, bottom-right,
    bottom-left in the tag's own frame). intr is accepted for API symmetry;
    corners are returned in raw (distorted) pixel coordinates.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    dic = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    params = cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    det = cv2.aruco.ArucoDetector(dic, params)
    corners, ids, _ = det.detectMarkers(gray)
    out: list[dict] = []
    if ids is None:
        return out
    for c, i in zip(corners, ids.reshape(-1), strict=True):
        out.append({"id": int(i), "corners": np.asarray(c, np.float64).reshape(4, 2)})
    return out


def default_hive_tag_corners(layout: Optional[dict] = None) -> dict[int, np.ndarray]:
    """PLACEHOLDER tag geometry in the field frame: {id: (4,3) corners}.

    NOT the real layout. Exact tag positions/orientations MUST be VERIFIED
    against Competition Manual Figure 9-17 / official CAD before use.

    Placeholder assumptions: each group of 4 tags (one per CELL bottom, ids in
    field_constants.APRILTAG_IDS) forms a 2x2 grid of APRILTAG_SIZE tags,
    lying flat (facing -Z, corners listed in ArUco order as seen from below),
    centered under the CELL at (hive_x, +/- BEAM_HALF_LENGTH, z).

    layout: optional dict overriding any of
      'z': height of the tag plane (default 10.0, a guess),
      'pitch': center-to-center tag spacing (default 5.0),
      'group_centers': {(alliance, end): (x, y)} overriding the group center.
    Audience end is assumed to be -Y, far end +Y (VERIFY).
    """
    layout = layout or {}
    z = float(layout.get("z", 10.0))
    pitch = float(layout.get("pitch", 5.0))
    centers = layout.get("group_centers", {})
    s = fc.APRILTAG_SIZE / 2.0
    out: dict[int, np.ndarray] = {}
    for (alliance, end), ids in fc.APRILTAG_IDS.items():
        hx = fc.RED_HIVE_X if alliance == "red" else fc.BLUE_HIVE_X
        hy = fc.BEAM_HALF_LENGTH * (1.0 if end == "far" else -1.0)
        cx, cy = centers.get((alliance, end), (hx, hy))
        for k, tid in enumerate(ids):
            tx = cx + (k % 2 - 0.5) * pitch
            ty = cy + (k // 2 - 0.5) * pitch
            # Viewed from below (+Z looking up) with x to the right, tag-up is
            # +Y: TL, TR, BR, BL -> mirrored in x relative to a top-down view.
            out[tid] = np.array(
                [
                    [tx + s, ty + s, z],
                    [tx - s, ty + s, z],
                    [tx - s, ty - s, z],
                    [tx + s, ty - s, z],
                ],
                dtype=np.float64,
            )
    return out


def solve_extrinsics_from_apriltags(
    intr: CameraIntrinsics,
    detections: list[dict],
    tag_poses: dict[int, np.ndarray],
    cam_id: str,
) -> CameraExtrinsics:
    """Build 2D-3D correspondences from detected tags known in tag_poses."""
    img, fld = [], []
    for d in detections:
        tid = int(d["id"])
        if tid not in tag_poses:
            continue
        img.append(np.asarray(d["corners"], np.float64).reshape(4, 2))
        fld.append(np.asarray(tag_poses[tid], np.float64).reshape(4, 3))
    if not img:
        raise ValueError("No detected AprilTag ids match tag_poses")
    return solve_extrinsics_from_points(intr, np.vstack(img), np.vstack(fld), cam_id)


def solve_extrinsics_from_tags(
    intr: CameraIntrinsics,
    image: np.ndarray,
    tag_defs: dict[int, np.ndarray],
    cam_id: str,
    min_tags: int = 2,
) -> tuple[CameraExtrinsics, dict]:
    """Detect the tags of a printed kit in `image` and solve the camera pose.

    tag_defs: {tag id: (4,3) field-frame corners in cv2.aruco order} (see
    hiveshot.tagkit.tag_defs()). All corners of all visible known tags are used.
    Returns (extrinsics, info) with info = {"tags_used": [ids], "tags_missing": [ids],
    "reprojection_px": rmse over all used corners, "max_corner_px", "rmse_in"}.
    Raises ValueError (plain-language message) if fewer than `min_tags` known tags are
    visible, e.g. "only 1 tag visible: 100; need 2".
    """
    dets = detect_apriltags(image, intr)
    seen: dict[int, np.ndarray] = {}
    for d in dets:
        tid = int(d["id"])
        if tid in tag_defs and tid not in seen:
            seen[tid] = np.asarray(d["corners"], np.float64).reshape(4, 2)
    used = sorted(seen)
    missing = sorted(set(tag_defs) - set(used))
    if len(used) < min_tags:
        if not used:
            raise ValueError(
                f"no known tags visible (looking for {sorted(tag_defs)}); need {min_tags}")
        word = "tag" if len(used) == 1 else "tags"
        raise ValueError(
            f"only {len(used)} {word} visible: {', '.join(map(str, used))}; need {min_tags}"
            f" (missing: {', '.join(map(str, missing))})")
    img = np.vstack([seen[t] for t in used])
    fld = np.vstack([np.asarray(tag_defs[t], np.float64).reshape(4, 3) for t in used])
    ext = solve_extrinsics_from_points(intr, img, fld, cam_id, use_ransac=False)
    rep = reprojection_report(intr, ext, img, fld)
    info = {
        "tags_used": used,
        "tags_missing": missing,
        "reprojection_px": float(rep["rmse_px"]),
        "max_corner_px": float(np.max(rep["per_point_px"])),
        "rmse_in": float(ext.rmse_in),
    }
    return ext, info


# --------------------------------------------------------------------------
# Triangulation
# --------------------------------------------------------------------------
def triangulate(
    intr_a: CameraIntrinsics,
    ext_a: CameraExtrinsics,
    uv_a: np.ndarray,
    intr_b: CameraIntrinsics,
    ext_b: CameraExtrinsics,
    uv_b: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Triangulate (N,2) pixel pairs. Returns (xyz (N,3), residual_in (N,)).

    xyz is the linear DLT solution (cv2.triangulatePoints on undistorted,
    normalized points). residual_in is the distance between the two
    back-projected rays at their mutual closest points (0 for perfect data).
    """
    single = np.asarray(uv_a).ndim == 1
    na = undistort_points(intr_a, np.asarray(uv_a, np.float64).reshape(-1, 2), True)
    nb = undistort_points(intr_b, np.asarray(uv_b, np.float64).reshape(-1, 2), True)
    Ra, ta = _rt(ext_a)
    Rb, tb = _rt(ext_b)
    Pa = np.hstack([Ra, ta.reshape(3, 1)])
    Pb = np.hstack([Rb, tb.reshape(3, 1)])
    X = cv2.triangulatePoints(Pa, Pb, na.T, nb.T)
    xyz = (X[:3] / X[3]).T

    # Ray distance.
    ca, cb = -Ra.T @ ta, -Rb.T @ tb
    da = np.hstack([na, np.ones((len(na), 1))]) @ Ra  # R^T d == d @ R
    db = np.hstack([nb, np.ones((len(nb), 1))]) @ Rb
    da /= np.linalg.norm(da, axis=1, keepdims=True)
    db /= np.linalg.norm(db, axis=1, keepdims=True)
    w = ca - cb
    b = np.sum(da * db, axis=1)
    d = da @ w
    e = db @ w
    den = 1.0 - b * b
    safe = den > 1e-12
    s = np.where(safe, (b * e - d) / np.where(safe, den, 1.0), 0.0)
    t = np.where(safe, (e - b * d) / np.where(safe, den, 1.0), e)
    pa = ca + s[:, None] * da
    pb = cb + t[:, None] * db
    resid = np.linalg.norm(pa - pb, axis=1)
    if single:
        return xyz[0], resid[0]
    return xyz, resid


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------
def save_calibration(
    path: str | Path,
    intr_list: Sequence[CameraIntrinsics],
    ext_list: Sequence[CameraExtrinsics],
) -> None:
    data = {
        "version": 1,
        "intrinsics": [
            {**i.__dict__, "dist": list(i.dist)} for i in intr_list
        ],
        "extrinsics": [
            {**e.__dict__, "rvec": list(e.rvec), "tvec": list(e.tvec)} for e in ext_list
        ],
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_calibration(path: str | Path) -> tuple[list[CameraIntrinsics], list[CameraExtrinsics]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    intr = [
        CameraIntrinsics(**{**d, "dist": tuple(d["dist"])}) for d in data.get("intrinsics", [])
    ]
    ext = [
        CameraExtrinsics(**{**d, "rvec": tuple(d["rvec"]), "tvec": tuple(d["tvec"])})
        for d in data.get("extrinsics", [])
    ]
    return intr, ext

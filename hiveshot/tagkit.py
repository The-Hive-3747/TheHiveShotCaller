"""Printed AprilTag calibration kit: four 36h11 tags on the HIVE frame top corners.

The operator prints the sheet (`write_tag_sheet_pdf`), cuts the four tags out, tapes
one at each top corner of the HIVE frame "label up", and the app solves each camera's
pose from the detected tag corners (`calib.solve_extrinsics_from_tags`). No clicking.

Geometry conventions (field frame, inches; +Y toward the audience, Z up)
------------------------------------------------------------------------
* Tag ids 100..103 correspond to `calib_targets.field_reference_points()` entries 5..8,
  the HIVE frame top corners: 100 = (-X,+Y), 101 = (+X,+Y), 102 = (-X,-Y), 103 = (+X,-Y).
* **Every tag lies in a vertical plane (constant Y) and faces +Y**, i.e. toward the
  audience side where the cameras stand. For the +Y corners this is the outward face of
  the audience-side top bar. For the -Y corners it is the face of the far-side top bar
  that looks toward the audience (a tag facing -Y would show its back to both cameras).
* The tag is mounted **flush with its frame corner**: the tag's outer top corner sits on
  the frame corner point and the tag hangs down and inward, so its center is
  (corner_x -/+ size/2 toward the frame center, corner_y, corner_z - size/2). A tag
  centered on the corner point itself would hang half in the air. Set FLUSH_MOUNT = False
  to center the tag on the corner point instead (then it needs a bracket).
* "Label up" means the tag's upright direction is +Z. Seen by a person standing on the
  audience side looking at the frame (looking toward -Y), the tag's right side is toward
  -X and its left side toward +X.
* Corner order of `tag_corners_xyz` is the cv2.aruco order, top-left, top-right,
  bottom-right, bottom-left of the tag as it looks when read upright (label up) from the
  front. Hence for a tag centered at (cx, y, cz) with half size s:
      TL = (cx + s, y, cz + s)   TR = (cx - s, y, cz + s)
      BR = (cx - s, y, cz - s)   BL = (cx + s, y, cz - s)
  The detector's corners are the corners of the outer black square (the 4.0 in).
* Print scale: the 4.0 in is the black square. Leave the white margin printed around it
  (at least 0.5 in) when cutting; the detector needs the white quiet zone.

All frame dimensions are CAD guesses (VERIFY, see calib_targets). If the tags are taped
where the real frame corners are but the model is off, the solved pose is off by the same
amount: tape-measure the real corner positions first.
"""

from __future__ import annotations

import math
import zlib
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from hiveshot import calib, calib_targets, field
from hiveshot import field_constants as fc

DICT_NAME = "DICT_APRILTAG_36h11"
TAG_SIZE_IN = 4.0
FLUSH_MOUNT = True
DPI = 300
PAGE_IN = (11.0, 8.5)            # letter, landscape; two tags per page
QUIET_IN = 0.5                   # white margin kept around each printed tag


@dataclass(frozen=True)
class KitTag:
    id: int
    point_name: str              # name of the calib_targets reference point (corner)
    size_in: float = TAG_SIZE_IN


_FRAME_NAMES = calib_targets.FRAME_TOP_NAMES   # (-X,+Y), (+X,+Y), (-X,-Y), (+X,-Y)
KIT_TAGS: tuple[KitTag, ...] = tuple(
    KitTag(100 + i, n) for i, n in enumerate(_FRAME_NAMES)
)


def _corner_xyz(tag: KitTag) -> np.ndarray:
    pts = dict(calib_targets.field_reference_points())
    return np.asarray(pts[tag.point_name], float)


def _by_id(tag) -> KitTag:
    if isinstance(tag, KitTag):
        return tag
    for t in KIT_TAGS:
        if t.id == int(tag):
            return t
    raise KeyError(f"unknown kit tag id {tag!r}; kit ids are {[t.id for t in KIT_TAGS]}")


def tag_center_xyz(tag) -> np.ndarray:
    """Center of the tag square in the field frame."""
    t = _by_id(tag)
    c = _corner_xyz(t).copy()
    if FLUSH_MOUNT:
        h = t.size_in / 2.0
        c[0] -= np.sign(c[0]) * h      # inward, toward the frame center
        c[2] -= h                      # downward
    return c


def tag_corners_xyz(tag) -> np.ndarray:
    """(4,3) field-frame corners in cv2.aruco order (TL, TR, BR, BL of the upright tag)."""
    t = _by_id(tag)
    cx, y, cz = tag_center_xyz(t)
    s = t.size_in / 2.0
    return np.array([[cx + s, y, cz + s],
                     [cx - s, y, cz + s],
                     [cx - s, y, cz - s],
                     [cx + s, y, cz - s]], float)


def tag_defs() -> dict[int, np.ndarray]:
    """{tag id: (4,3) corners}, the form `calib.solve_extrinsics_from_tags` takes."""
    return {t.id: tag_corners_xyz(t) for t in KIT_TAGS}


def tags_json() -> list[dict]:
    """Payload of GET /api/calib/tags."""
    return [{"id": t.id, "size_in": t.size_in, "name": t.point_name,
             "xyz_center": [float(v) for v in tag_center_xyz(t)],
             "corners_xyz": [[float(v) for v in p] for p in tag_corners_xyz(t)]}
            for t in KIT_TAGS]


def render_marker(tag_id: int, px: int) -> np.ndarray:
    """Gray image of the tag (black border included, no white margin)."""
    dic = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    return cv2.aruco.generateImageMarker(dic, int(tag_id), int(px), borderBits=1)


def _arrow_up(img: np.ndarray, x: int, y_top: int, y_bot: int) -> None:
    cv2.arrowedLine(img, (x, y_bot), (x, y_top), 0, 6, cv2.LINE_AA, tipLength=0.12)


def render_tag_pages() -> list[np.ndarray]:
    """Two landscape letter pages (300 dpi gray), two tags each."""
    W, H = int(PAGE_IN[0] * DPI), int(PAGE_IN[1] * DPI)
    font = cv2.FONT_HERSHEY_SIMPLEX
    px = int(round(TAG_SIZE_IN * DPI))
    pages = []
    for chunk in (KIT_TAGS[:2], KIT_TAGS[2:]):
        img = np.full((H, W), 255, np.uint8)
        slot_w = W // 2
        for k, t in enumerate(chunk):
            x0 = k * slot_w + (slot_w - px) // 2
            y0 = int(1.3 * DPI)
            img[y0:y0 + px, x0:x0 + px] = render_marker(t.id, px)
            cv2.putText(img, f"TAG {t.id}", (x0, y0 - int(0.75 * DPI)), font, 1.6, 0, 4,
                        cv2.LINE_AA)
            cv2.putText(img, t.point_name, (x0, y0 - int(0.3 * DPI)), font, 0.95, 0, 2,
                        cv2.LINE_AA)
            ax = x0 - int(0.3 * DPI)
            _arrow_up(img, ax, y0, y0 + px // 2)
            cv2.putText(img, "THIS", (ax - int(0.55 * DPI), y0 + px // 2 + int(0.35 * DPI)), font,
                        0.8, 0, 2, cv2.LINE_AA)
            cv2.putText(img, "EDGE UP", (ax - int(0.7 * DPI), y0 + px // 2 + int(0.6 * DPI)), font,
                        0.8, 0, 2, cv2.LINE_AA)
            cv2.putText(img, "Tape label up, outer top corner on the frame corner.",
                        (x0 - int(0.4 * DPI), y0 + px + int(0.45 * DPI)), font, 0.7, 0, 2,
                        cv2.LINE_AA)
            cv2.putText(img, "Cut leaving the white border (0.5 in or more).",
                        (x0 - int(0.4 * DPI), y0 + px + int(0.75 * DPI)), font, 0.7, 0, 2,
                        cv2.LINE_AA)
        # print-scale check: a 4.00 in line with end ticks
        ly = H - int(0.7 * DPI)
        lx = (W - px) // 2
        cv2.line(img, (lx, ly), (lx + px, ly), 0, 5)
        cv2.line(img, (lx, ly - 25), (lx, ly + 25), 0, 5)
        cv2.line(img, (lx + px, ly - 25), (lx + px, ly + 25), 0, 5)
        cv2.putText(img, f"This line must measure {TAG_SIZE_IN:.2f} in. Print at 100% / Actual "
                    "size, not fit to page.", (lx - int(0.6 * DPI), ly + int(0.45 * DPI)), font,
                    0.75, 0, 2, cv2.LINE_AA)
        pages.append(img)
    return pages


def _build_pdf_pages(pages: list[np.ndarray], page_in: tuple[float, float]) -> bytes:
    """Hand-written multi-page PDF, one full-page gray image per page."""
    pw, ph = page_in[0] * 72.0, page_in[1] * 72.0
    n = len(pages)
    objs: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{3 + 3 * i} 0 R" for i in range(n))
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode())
    for i, g in enumerate(pages):
        cont_id, img_id = 4 + 3 * i, 5 + 3 * i
        h, w = g.shape
        content = f"q {pw:.3f} 0 0 {ph:.3f} 0 0 cm /Im0 Do Q".encode()
        stream = zlib.compress(g.tobytes(), 9)
        objs.append((f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {pw:.3f} {ph:.3f}] "
                     f"/Resources << /XObject << /Im0 {img_id} 0 R >> >> "
                     f"/Contents {cont_id} 0 R >>").encode())
        objs.append(b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content
                    + b"\nendstream")
        objs.append((f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} "
                     f"/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode "
                     f"/Length {len(stream)} >>\nstream\n").encode() + stream + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
            ).encode()
    return bytes(out)


def tag_sheet_pdf_bytes() -> bytes:
    return _build_pdf_pages(render_tag_pages(), PAGE_IN)


def write_tag_sheet_pdf(path: str | Path) -> Path:
    """Write the printable tag sheet (2 landscape letter pages, 2 tags each, each tag
    4.00 in with its quiet zone, labeled with its frame corner, an "edge up" arrow and a
    4.00 in ruler line for the print-scale check). Also writes page PNGs next to it
    (<stem>_p1.png, <stem>_p2.png). Returns the PDF path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pages = render_tag_pages()
    path.write_bytes(_build_pdf_pages(pages, PAGE_IN))
    for i, g in enumerate(pages, 1):
        cv2.imwrite(str(path.with_name(f"{path.stem}_p{i}.png")), g)
    return path


# ======================================================================================
# Learning the field's own HIVE tags (ids 30-45) and inferring the HIVE state from them
# ======================================================================================
HIVE_TAG_IDS = tuple(sorted(i for ids in fc.HIVE_TAG_CLUSTERS.values() for i in ids))
_CLUSTER_OF = {i: name for name, ids in fc.HIVE_TAG_CLUSTERS.items() for i in ids}


def _hive_detections(image: np.ndarray) -> dict[int, np.ndarray]:
    return {d["id"]: np.asarray(d["corners"], float).reshape(4, 2)
            for d in calib.detect_apriltags(image) if d["id"] in _CLUSTER_OF}


def learn_hive_tags(intr_a, ext_a, img_a, intr_b, ext_b, img_b,
                    alliance: str | None = None, state=None
                    ) -> tuple[dict[int, np.ndarray], dict]:
    """Triangulate the corners of every HIVE tag (ids 30-45) seen by BOTH calibrated cameras.

    Returns (learned, info): learned = {id: (4,3) field-frame corners in cv2.aruco order},
    info = {"visible_per_camera": {cam_id: [ids]}, "ids_learned": [...], "max_residual_in":
    worst ray-to-ray distance over all learned corners (0.0 if none)}. Tags seen by only
    one camera are reported in visible_per_camera but not learned.

    If `alliance` and `state` (a field.HiveState) are given, the learned corners of the UP
    cell's tags are compared with the computed ones (`up_cell_tag_corners`) and
    info["error_vs_computed_in"] = {id: worst corner error in inches} (verification of the
    computed geometry on the real field; the DOWN cell has no computed geometry, so its tags
    are only learned).
    """
    da, db = _hive_detections(img_a), _hive_detections(img_b)
    learned: dict[int, np.ndarray] = {}
    worst = 0.0
    for tid in sorted(set(da) & set(db)):
        xyz, res = calib.triangulate(intr_a, ext_a, da[tid], intr_b, ext_b, db[tid])
        learned[tid] = np.asarray(xyz, float).reshape(4, 3)
        worst = max(worst, float(np.max(res)))
    info = {"visible_per_camera": {intr_a.cam_id: sorted(da), intr_b.cam_id: sorted(db)},
            "ids_learned": sorted(learned), "max_residual_in": worst}
    if alliance is not None and state is not None:
        comp = up_cell_tag_corners(alliance, state.up_cell)
        info["error_vs_computed_in"] = {
            tid: float(np.linalg.norm(learned[tid] - comp[tid], axis=1).max())
            for tid in sorted(learned) if tid in comp}
    return learned, info


def hive_tag_defs_from_learned(learned: dict) -> dict[int, np.ndarray]:
    """Learned HIVE tag corners in the format `calib.solve_extrinsics_from_tags` takes.
    Only valid for the HIVE state the tags were learned in."""
    return {int(i): np.asarray(c, float).reshape(4, 3).copy()
            for i, c in learned.items() if int(i) in _CLUSTER_OF}


def row_height_in(learned: dict, cluster_name: str) -> float | None:
    """Mean height (z, inches) of the tag corners of a cluster ('red_audience', ...) among
    the learned tags; None if no tag of that cluster is in `learned`."""
    ids = fc.HIVE_TAG_CLUSTERS[cluster_name]
    zs = [np.asarray(learned[i], float).reshape(4, 3)[:, 2] for i in ids if i in learned]
    return float(np.mean(zs)) if zs else None


def _observed_centers(detections_per_cam: dict, calib_per_cam: dict) -> dict[int, np.ndarray]:
    """Field-frame center of each HIVE tag seen by at least one calibrated camera:
    triangulated when two cameras see it, else a single-camera square-tag PnP."""
    seen: dict[int, dict[str, np.ndarray]] = {}
    for cam_id, dets in detections_per_cam.items():
        if cam_id not in calib_per_cam:
            continue
        for d in dets:
            if int(d["id"]) in _CLUSTER_OF:
                seen.setdefault(int(d["id"]), {})[cam_id] = np.asarray(d["corners"],
                                                                       float).reshape(4, 2)
    out: dict[int, np.ndarray] = {}
    for tid, per in seen.items():
        cams = sorted(per)
        if len(cams) >= 2:
            (ia, ea), (ib, eb) = calib_per_cam[cams[0]], calib_per_cam[cams[1]]
            xyz, _ = calib.triangulate(ia, ea, per[cams[0]], ib, eb, per[cams[1]])
            out[tid] = np.asarray(xyz, float).reshape(4, 3).mean(axis=0)
            continue
        intr, ext = calib_per_cam[cams[0]]
        s = fc.APRILTAG_SIZE / 2.0
        obj = np.array([[-s, s, 0], [s, s, 0], [s, -s, 0], [-s, -s, 0]], np.float64)
        ok, rvec, tvec = cv2.solvePnP(obj, per[cams[0]], calib.camera_matrix(intr),
                                      calib.dist_coeffs(intr), flags=cv2.SOLVEPNP_IPPE_SQUARE)
        if not ok:
            continue
        R = cv2.Rodrigues(np.array(ext.rvec, float))[0]
        out[tid] = R.T @ (tvec.reshape(3) - np.array(ext.tvec, float))
    return out


# ---- computed geometry of the UP cell's tags --------------------------------------------
STICKER_TILT_DEG = 30.0


def _fallback_up_cell_tag_corners(alliance: str, which: str) -> dict[int, np.ndarray]:
    """Up-cell tag geometry from the official figures (docs/research_apriltags.md), used when
    `field.hive_tag_corners` is not available. The sticker lies on the CELL floor, its
    tag row center 7.188 in behind the opening's bottom edge (TAG_ROW_FROM_CELL_FRONT)
    along the floor, facing the tiles; the sticker's bottom edge is toward the field center.
      row center = c_low + 7.188 * d_floor, d_floor = (0, -ys*cos30, -sin30)
      sticker normal n = (0, ys*sin30, -cos30), sticker up u = (0, ys*cos30, sin30)
      (ys = +1 audience cell, -1 far cell); a tag's right vector is (-n) x u (the viewer
      looks along -n): -X for the audience cell, +X for the far cell. Tag k is centered at
      row center + HIVE_TAG_ROW_OFFSETS_IN[k] * r (ids ascend toward image-right, the same
      right-handed convention as field.hive_tag_corners; VERIFY the direction on the real
      field with learn_hive_tags(alliance, state)). The sticker plane is 0.12 in outside the
      floor (field.TAG_STICKER_BELOW_FLOOR). Corners in cv2.aruco order TL, TR, BR, BL of the upright sticker.
    """
    st = field.HiveState(alliance, which)
    poly = field.cell_opening_polygon(alliance, which, st)
    c_low = 0.5 * (poly[0] + poly[1])
    ys = 1.0 if which == "audience" else -1.0
    t = math.radians(STICKER_TILT_DEG)
    d_floor = np.array([0.0, -ys * math.cos(t), -math.sin(t)])
    n = np.array([0.0, ys * math.sin(t), -math.cos(t)])
    u = np.array([0.0, ys * math.cos(t), math.sin(t)])
    r = np.cross(-n, u)
    ctr = c_low + fc.TAG_ROW_FROM_CELL_FRONT * d_floor + 0.12 * n
    ids = fc.HIVE_TAG_CLUSTERS[f"{alliance}_{which}"]
    h = fc.APRILTAG_SIZE / 2.0
    out = {}
    for tid, off in zip(ids, fc.HIVE_TAG_ROW_OFFSETS_IN, strict=True):
        c = ctr + off * r
        out[tid] = np.array([c + h * u - h * r, c + h * u + h * r,
                             c - h * u + h * r, c - h * u - h * r])
    return out


def up_cell_tag_corners(alliance: str = "red", which: str = "audience") -> dict[int, np.ndarray]:
    """{id: (4,3)} computed corners of the tags on the UP cell `which` of `alliance`.
    Uses `field.hive_tag_corners(alliance, which, HiveState)` when it exists, otherwise the
    fallback derived from the official constants."""
    fn = getattr(field, "hive_tag_corners", None)
    if fn is not None:
        got = fn(alliance, which, field.HiveState(alliance, which))
        return {int(k): np.asarray(v, float).reshape(4, 3) for k, v in got.items()}
    return _fallback_up_cell_tag_corners(alliance, which)


def hive_tag_defs(alliance: str = "red", state=None, learned: dict | None = None
                  ) -> dict[int, np.ndarray]:
    """tag_defs for the HIVE tags: the computed tags of the UP cell of `alliance` (state is a
    field.HiveState, default audience up), merged with any learned tags (e.g. the down
    cell's), computed values winning on a clash."""
    st = state or field.HiveState(alliance, "audience")
    out = hive_tag_defs_from_learned(learned or {})
    out.update(up_cell_tag_corners(alliance, st.up_cell))
    return out


def combined_tag_defs(alliance: str = "red", state=None, learned: dict | None = None
                      ) -> dict[int, np.ndarray]:
    """Kit tags (100-103) plus HIVE tags: the dict `calib.solve_extrinsics_from_tags` takes
    to calibrate from whatever subset of both is visible."""
    out = tag_defs()
    out.update(hive_tag_defs(alliance, state, learned))
    return out


def tag_up_vector_field(corners, intr, ext, size_in: float = fc.APRILTAG_SIZE) -> np.ndarray:
    """Direction (unit, field frame) of the tag's own "up" (bottom edge to top edge) from a
    single-camera square-tag pose. Its z sign is the SDK's roll test: z > 0 (roll within
    +-90 deg, right side up) for a tag on the UP cell, z < 0 on the DOWN cell."""
    s = size_in / 2.0
    obj = np.array([[-s, s, 0], [s, s, 0], [s, -s, 0], [-s, -s, 0]], np.float64)
    n, rvecs, tvecs, errs = cv2.solvePnPGeneric(
        obj, np.asarray(corners, np.float64).reshape(4, 2), calib.camera_matrix(intr),
        calib.dist_coeffs(intr), flags=cv2.SOLVEPNP_IPPE_SQUARE)
    if not n:
        raise ValueError("tag pose failed")
    k = int(np.argmin(np.asarray(errs, float).reshape(-1)))
    up_cam = cv2.Rodrigues(rvecs[k])[0] @ np.array([0.0, 1.0, 0.0])
    R = cv2.Rodrigues(np.array(ext.rvec, float))[0]
    v = R.T @ up_cam
    return v / np.linalg.norm(v)


def up_cells_from_tags(detections_per_cam: dict, calib_per_cam: dict,
                       pivot_height_in: float = fc.PIVOT_HEIGHT) -> dict:
    """Which CELL is up, straight from the visible tags (no learned data needed).

    A cluster whose tags are seen right side up (tag up vector z > 0, the SDK's |roll| < 90)
    is on the UP cell. Returns {"clusters": {name: {"upright": bool, "upright_frac": f,
    "height_in": z|None, "height_agrees": bool|None}}, "up": {alliance: "audience"|"far"|None},
    "confidence": 0..1} (confidence 1 when roll and row height vs the pivot agree on every
    cluster, 0.5 per conflict; 0 when nothing is visible)."""
    ups: dict[str, list[bool]] = {}
    for cam_id, dets in detections_per_cam.items():
        if cam_id not in calib_per_cam:
            continue
        intr, ext = calib_per_cam[cam_id]
        for d in dets:
            tid = int(d["id"])
            if tid in _CLUSTER_OF:
                try:
                    v = tag_up_vector_field(d["corners"], intr, ext)
                except ValueError:
                    continue
                ups.setdefault(_CLUSTER_OF[tid], []).append(bool(v[2] > 0))
    heights: dict[str, list[float]] = {}
    for tid, c in _observed_centers(detections_per_cam, calib_per_cam).items():
        heights.setdefault(_CLUSTER_OF[tid], []).append(float(c[2]))
    clusters, up, conf = {}, {"red": None, "blue": None}, 1.0
    for name, flags in ups.items():
        frac = float(np.mean(flags))
        h = float(np.mean(heights[name])) if name in heights else None
        agree = None if h is None else ((h > pivot_height_in) == (frac > 0.5))
        clusters[name] = {"upright": frac > 0.5, "upright_frac": frac, "height_in": h,
                          "height_agrees": agree}
        if agree is False:
            conf *= 0.5
        alliance, which = name.split("_")
        if frac > 0.5:
            up[alliance] = which
    if not clusters:
        return {"clusters": {}, "up": up, "confidence": 0.0}
    return {"clusters": clusters, "up": up, "confidence": conf}


def infer_hive_state(learned_by_state: dict | None, detections_per_cam: dict,
                     calib_per_cam: dict | None = None,
                     pivot_height_in: float = fc.PIVOT_HEIGHT, alliance: str | None = None):
    """Which HIVE state is on the field right now? Returns (state_key | None, confidence 0..1).

    learned_by_state: {state_key: learned} (each from `learn_hive_tags` with the HIVE
        settled in that state), or None / empty to use the computed-geometry rule alone, in
        which case the key is "<alliance>/<up cell>" (e.g. "red/audience").
    detections_per_cam: {cam_id: detect_apriltags() output} for the current frames.
    calib_per_cam: {cam_id: (intr, ext)} of the calibrated cameras. With it:
      * a cluster seen right side up (tag up vector z > 0, the SDK's |roll| < 90 deg) is on
        the UP cell (`up_cells_from_tags`); a conflict between roll and row height vs the
        pivot (43.95 in) halves the confidence;
      * with learned_by_state, the height of every visible tag row (triangulated if two
        cameras see a tag, else single-camera PnP) picks the nearest learned state.
      Without calibration only the visible ids are compared with the ids each state learned
      (Jaccard score, confidence capped at 0.6). No visible HIVE tag -> (None, 0.0).
    alliance: restrict the roll rule to one alliance (default: the first alliance with an
        upright cluster, red before blue).
    """
    vis = {int(d["id"]) for dets in detections_per_cam.values() for d in dets
           if int(d["id"]) in _CLUSTER_OF}
    if not vis:
        return None, 0.0
    roll = up_cells_from_tags(detections_per_cam, calib_per_cam) if calib_per_cam else None
    if not learned_by_state:
        if roll is None or roll["confidence"] <= 0:
            return None, 0.0
        for al in ((alliance,) if alliance else ("red", "blue")):
            if roll["up"].get(al):
                return f"{al}/{roll['up'][al]}", float(roll["confidence"])
        return None, 0.0
    jac = {k: len(vis & set(L)) / len(vis | set(L)) for k, L in learned_by_state.items()}

    heights: dict[str, list[float]] = {}
    if calib_per_cam:
        for tid, c in _observed_centers(detections_per_cam, calib_per_cam).items():
            heights.setdefault(_CLUSTER_OF[tid], []).append(float(c[2]))
    obs = {name: float(np.mean(z)) for name, z in heights.items()}
    if not obs:
        ranked = sorted(jac.items(), key=lambda kv: -kv[1])
        best = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else 0.0
        if best[1] <= 0.0:
            return None, 0.0
        return best[0], float(min(0.6, 0.6 * (best[1] - second) + 0.1 * best[1]))

    dist: dict = {}
    for k, L in learned_by_state.items():
        ds = [abs(h - lh) for name, h in obs.items()
              if (lh := row_height_in(L, name)) is not None]
        dist[k] = float(np.mean(ds)) if ds else float("inf")
    ranked = sorted(dist.items(), key=lambda kv: (kv[1], -jac[kv[0]]))
    best_k, best_d = ranked[0]
    if not np.isfinite(best_d):
        return None, 0.0
    second_d = ranked[1][1] if len(ranked) > 1 else float("inf")
    conf = 1.0 if not np.isfinite(second_d) else 1.0 - best_d / (best_d + second_d + 1e-9)
    # cross-check: every observed row must be on the same side of the pivot as learned
    for name, h in obs.items():
        lh = row_height_in(learned_by_state[best_k], name)
        if lh is not None and (h > pivot_height_in) != (lh > pivot_height_in):
            conf *= 0.5
    # independent roll evidence: an upright cluster must be above the pivot in the chosen state
    if roll is not None:
        for name, c in roll["clusters"].items():
            lh = row_height_in(learned_by_state[best_k], name)
            if lh is not None and c["upright"] != (lh > pivot_height_in):
                conf *= 0.5
    return best_k, float(max(0.0, min(1.0, conf)))

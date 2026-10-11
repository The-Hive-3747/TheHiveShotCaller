"""Printed AprilTag calibration kit: four 36h11 tags on real features of the HIVE frame.

The operator prints the sheet (`write_tag_sheet_pdf`), cuts the tags out, tapes them on the
HIVE frame as described below, and the app solves each camera's pose from the detected tag
corners (`calib.solve_extrinsics_from_tags`). No clicking.

The official frame is NOT a box (CAD, `field_constants` block "Frame (CAD-extracted)"): at each
X end an A-frame, two legs rising inward from a foot bar on the tiles to an apex, the two apexes
joined by a 24 in crossbar along X at height 41.45 in, with a logo panel on the audience and
the far face of the crossbar region. The kit uses features that exist on that structure.

Size: the default tag size is DEFAULT_TAG_SIZE_IN = 6.0 in (the black square), one tag per
letter page. Every function takes `size_in` to override it (up to 7.5 in fits a page with its
white border, and the panel tags fit only up to 6.4 in).

HIVE state: calibrate with BOTH HIVEs tipped by hand so that both audience CELLs are up
(`CALIBRATION_HIVE_STATES`, `field.CALIBRATION_STATE`). In the match-start state (red audience CELL
up, blue far CELL up) the blue audience CELL is DOWN and its solid body stands between the
audience-side cameras and tag 100 (and half of tag 101 from camera A), see `placement.kit_view`.

Tags (field frame, inches; +Y toward the audience, Z up; positions from
`field.frame_reference_points()` and the CAD frame constants)
------------------------------------------------------------------------------------------
* 100 and 101, "panel tags": 100 on the -X side, 101 on the +X side, **lying flat on the
  audience (+Y) logo panel**. The panel is a flat plate that leans 24 deg with the legs
  (`field.logo_panel_face("audience")`: sticker face bottom corners (+-14.58, 4.29, 34.12), top
  corners (+-13.22, 1.67, 40.02), slant height 6.46 in, outward normal (0, 0.9135, 0.4067): it
  faces the audience AND up), standing in front of the crossbar; a tag hung from the 1 in
  crossbar would be hidden behind it. The tag lies on the plate, label up (upright direction = up
  the slope), its **top edge flush with the top edge of the panel** and its outer edge
  PANEL_EDGE_MARGIN_IN (0.22 in) inside the panel's top corner so that the tag stays on the
  trapezoid (the top edge is only 26.4 in wide: a 6 in tag centered at the crossbar end x = 12
  would overhang by 1.8 in). Center x = +-(13.22 - 0.22 - size/2) = +-10.0 for a 6 in tag, 2 in
  inboard of the crossbar end. The sticker's bottom tabs and chamfered top corners are not in
  the quad and are not used.
* 102 and 103, "base tags": 102 at the (-X, +Y) and 103 at the (+X, +Y) audience-side outer base
  corner of the frame (foot bar outer corner (+-24.73, 19.47, 0) on the tiles). The tag **stands on
  the tile leaning back by BASE_TILT_DEG = 20 deg**. The CARD (the black square plus its white
  border, cut exactly CARD_BORDER_IN = 0.5 in outside the black square) stands on its bottom edge,
  which lies on the tile at y = 19.47 + 2.15 tan(20 deg) = 20.25 in (so the card rests against the
  top edge of the foot bar end, 2.15 in high); **the black square's bottom edge is CARD_BORDER_IN
  up the slope from the tile** (0.47 in high, 0.17 in toward the frame), its outer edge is flush
  with the foot bar's outer face (x = +-24.73, the border hangs outside), and the top leans toward
  the frame (-Y). A foam wedge holds the card: see `STAND_WEDGE_IN`, `STAND_WEDGE_X_IN` (inboard of the foot bar). The face normal is (0, cos 20, sin 20): facing the audience and
  tilted up so that cameras at 20 to 30 in lens height look at it nearly square.
* "Label up" means the tag's upright direction (bottom edge to top edge) points up: up the
  slope (0, -0.407, 0.914) for 100 and 101, (0, -sin 20, cos 20) for 102 and 103. A person standing on the audience side looking at the
  frame sees the tag's right side toward -X.
* Corner order of `tag_corners_xyz` is the cv2.aruco order, top-left, top-right, bottom-right,
  bottom-left of the tag as it looks when read upright from the front. With u = upright direction,
  n = face normal, r = u x n (right), half size s: TL = c + s u - s r, TR = c + s u + s r,
  BR = c - s u + s r, BL = c - s u - s r. The detector's corners are the corners of the outer
  black square (the tag size).
* Print scale: the tag size is the black square. Leave the white margin printed around it
  (at least QUIET_IN = 0.5 in) when cutting; the detector needs the white quiet zone.

Tolerance: the solved pose is only as good as the tape placement. Measure each tag's position with
a tape measure to within 0.25 in (and its tilt to 0.5 deg) before calibrating; see
docs/calibration.md for the pose error to expect from 0.5 in / 1 deg and 1 in / 2 deg mounting
errors.
"""

from __future__ import annotations

import math
import zlib
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from hiveshot import calib, field
from hiveshot import field_constants as fc

DICT_NAME = "DICT_APRILTAG_36h11"
DEFAULT_TAG_SIZE_IN = 6.0
TAG_SIZE_IN = DEFAULT_TAG_SIZE_IN
BASE_TILT_DEG = 20.0             # base tags lean back this far from vertical
PANEL_EDGE_MARGIN_IN = 0.22      # panel tags stay this far inside the panel's top corners
CARD_BORDER_IN = 0.5             # white border of the printed card, cut exactly on this line
# Calibrate with both audience CELLs up (tip both HIVEs by hand); match start has the blue far
# CELL up, which puts the blue audience CELL's body in front of tag 100 for both cameras.
CALIBRATION_HIVE_STATES = (("red", "audience"), ("blue", "audience"))
# Foam-core wedge behind the card of a base tag: (width along X, depth along Y at the tile, height).
# Its vertical face is toward the frame, its slanted face (20 deg from vertical, tan 20 = 2.0 / 5.5)
# lies under the back of the card; it fills only the 4 in of the card inboard of the foot bar
# (x = 22.75 to 18.73), the outer 2 in of the card rest on the foot bar end.
STAND_WEDGE_IN = (4.0, 2.0, 5.5)
# |x| range of the wedge behind a base card: INBOARD, from the black square's inner edge (18.73) to the
# foot bar's inner face (22.75), so it stands on the tile beside the 1.98 in wide foot bar and clears it
STAND_WEDGE_X_IN = (fc.FRAME_BASE_X_OUTER - 6.0, fc.FRAME_BASE_X_INNER)
DPI = 300
PAGE_IN = (8.5, 11.0)            # letter, portrait; one tag per page
QUIET_IN = 0.5                   # white margin kept around each printed tag


@dataclass(frozen=True)
class KitTag:
    id: int
    point_name: str              # the frame feature the tag belongs to
    size_in: float = DEFAULT_TAG_SIZE_IN
    kind: str = "panel"          # "panel": flat on the leaning logo panel; "base": on the tiles


def kit_tags(size_in: float | None = None) -> tuple[KitTag, ...]:
    """The kit at `size_in` (default 6.0 in): 100/101 lying flat on the slanted audience logo
    panel (-X/+X side, centers x = +-10 for 6 in tags), 102/103 standing at the -X/+X
    audience-side base corners."""
    s = DEFAULT_TAG_SIZE_IN if size_in is None else float(size_in)
    return (
        KitTag(100, "Audience logo panel, -X side (flat on the slanted panel)", s, "panel"),
        KitTag(101, "Audience logo panel, +X side (flat on the slanted panel)", s, "panel"),
        KitTag(102, "Frame base corner (-X, +Y), standing tilted back 20 deg", s, "base"),
        KitTag(103, "Frame base corner (+X, +Y), standing tilted back 20 deg", s, "base"),
    )


KIT_TAGS: tuple[KitTag, ...] = kit_tags()
_FEATURE = {102: "Frame base corner (-X, +Y)", 103: "Frame base corner (+X, +Y)"}


def _by_id(tag, size_in: float | None = None) -> KitTag:
    if isinstance(tag, KitTag):
        return tag
    for t in kit_tags(size_in):
        if t.id == int(tag):
            return t
    raise KeyError(f"unknown kit tag id {tag!r}; kit ids are {[t.id for t in kit_tags(size_in)]}")


def _frame_point(tag_id: int) -> np.ndarray:
    return np.asarray(dict(field.frame_reference_points())[_FEATURE[tag_id]], float)


def _pose(tag: KitTag) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(center, upright direction u, face normal n) of a kit tag in the field frame."""
    h = tag.size_in / 2.0
    if tag.kind == "panel":
        quad, n = field.logo_panel_face("audience")           # BL(+X), BR(-X), TR(-X), TL(+X)
        n = np.asarray(n, float)
        bottom, top = 0.5 * (quad[0] + quad[1]), 0.5 * (quad[2] + quad[3])
        slant = float(np.linalg.norm(top - bottom))
        if tag.size_in > slant - 1e-9:
            raise ValueError(f"a {tag.size_in:g} in tag does not fit the {slant:.2f} in panel")
        u = (top - bottom) / slant                             # up the slope, in the plane
        n = n - float(n @ u) * u                               # orthonormal frame (u, n)
        n /= np.linalg.norm(n)
        half_top = float(abs(quad[3][0]))                      # half width of the top edge
        sx = -1.0 if tag.id == 100 else 1.0
        cx = sx * (half_top - PANEL_EDGE_MARGIN_IN - h)
        c = np.array([cx, top[1], top[2]]) - h * u             # top edge flush with the panel top
        # the lower corners must stay on the trapezoid too (it widens toward the bottom)
        assert abs(cx) + h <= half_top - PANEL_EDGE_MARGIN_IN + 1e-9
    else:
        a = _frame_point(tag.id)
        t = math.radians(BASE_TILT_DEG)
        u = np.array([0.0, -math.sin(t), math.cos(t)])
        n = np.array([0.0, math.cos(t), math.sin(t)])
        y_b = a[1] + fc.FRAME_BASE_HEIGHT * math.tan(t)           # leans on the foot bar end
        card_bottom = np.array([a[0] - math.copysign(h, a[0]), y_b, 0.0])
        c = card_bottom + (CARD_BORDER_IN + h) * u                # black square starts above the border
    return c, u, n


def tag_center_xyz(tag, size_in: float | None = None) -> np.ndarray:
    """Center of the tag square in the field frame."""
    return _pose(_by_id(tag, size_in))[0]


def tag_normal_xyz(tag, size_in: float | None = None) -> np.ndarray:
    """Unit normal of the tag face (pointing toward the viewer)."""
    return _pose(_by_id(tag, size_in))[2]


def tag_corners_xyz(tag, size_in: float | None = None) -> np.ndarray:
    """(4,3) field-frame corners in cv2.aruco order (TL, TR, BR, BL of the upright tag)."""
    t = _by_id(tag, size_in)
    c, u, n = _pose(t)
    r = np.cross(u, n)
    h = t.size_in / 2.0
    return np.array([c + h * u - h * r, c + h * u + h * r, c - h * u + h * r, c - h * u - h * r])


def tag_defs(size_in: float | None = None) -> dict[int, np.ndarray]:
    """{tag id: (4,3) corners}, the form `calib.solve_extrinsics_from_tags` takes."""
    return {t.id: tag_corners_xyz(t) for t in kit_tags(size_in)}


def tags_json(size_in: float | None = None) -> list[dict]:
    """Payload of GET /api/calib/tags."""
    return [{"id": t.id, "size_in": t.size_in, "name": t.point_name, "kind": t.kind,
             "xyz_center": [float(v) for v in tag_center_xyz(t)],
             "normal": [float(v) for v in tag_normal_xyz(t)],
             "corners_xyz": [[float(v) for v in p] for p in tag_corners_xyz(t)]}
            for t in kit_tags(size_in)]


def render_marker(tag_id: int, px: int) -> np.ndarray:
    """Gray image of the tag (black border included, no white margin)."""
    dic = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    return cv2.aruco.generateImageMarker(dic, int(tag_id), int(px), borderBits=1)


def _dashed_rect(img: np.ndarray, xa: int, ya: int, xb: int, yb: int, dash: int = 24) -> None:
    for x in range(xa, xb, 2 * dash):
        cv2.line(img, (x, ya), (min(x + dash, xb), ya), 0, 3)
        cv2.line(img, (x, yb), (min(x + dash, xb), yb), 0, 3)
    for y in range(ya, yb, 2 * dash):
        cv2.line(img, (xa, y), (xa, min(y + dash, yb)), 0, 3)
        cv2.line(img, (xb, y), (xb, min(y + dash, yb)), 0, 3)


def _arrow_up(img: np.ndarray, x: int, y_top: int, y_bot: int, width: int = 6) -> None:
    cv2.arrowedLine(img, (x, y_bot), (x, y_top), 0, width, cv2.LINE_AA, tipLength=0.12)


_HOW = {
    "panel": ("Lay it flat on the SLANTED audience logo panel, top edge flush with the top of the",
              "panel, outer edge 0.2 in inside the panel's top corner (center 10.0 in from the middle)."),
    "base": ("Cut ON the dashed line (0.5 in border). Stand the card on the tile at the base corner,",
             "black square flush with the foot bar's outer face, leaning back 20 deg on its foam wedge."),
}


def render_tag_pages(size_in: float | None = None) -> list[np.ndarray]:
    """One portrait letter page (300 dpi gray) per tag: the tag (`size_in`, default 6.0 in)
    with a white margin of at least QUIET_IN, its label and frame feature, an arrow "this
    edge up", taping instructions and a print-scale ruler line of the same length as the
    tag."""
    tags = kit_tags(size_in)
    size = tags[0].size_in
    if size + 2 * QUIET_IN > PAGE_IN[0]:
        raise ValueError(f"a {size:g} in tag plus its {QUIET_IN} in quiet zone does not fit on "
                         f"a {PAGE_IN[0]} in wide page")
    W, H = int(PAGE_IN[0] * DPI), int(PAGE_IN[1] * DPI)
    font = cv2.FONT_HERSHEY_SIMPLEX
    px = int(round(size * DPI))
    bw = int(round(CARD_BORDER_IN * DPI))
    pages = []
    for t in tags:
        img = np.full((H, W), 255, np.uint8)
        x0, y0 = (W - px) // 2, int(2.1 * DPI)
        img[y0:y0 + px, x0:x0 + px] = render_marker(t.id, px)
        _dashed_rect(img, x0 - bw, y0 - bw, x0 + px + bw, y0 + px + bw)   # cut line, CARD_BORDER_IN out
        cv2.putText(img, f"TAG {t.id}   ({size:g} in)", (x0, int(0.8 * DPI)), font, 1.8, 0, 4,
                    cv2.LINE_AA)
        cv2.putText(img, t.point_name, (x0, int(1.3 * DPI)), font, 0.8, 0, 2, cv2.LINE_AA)
        cv2.putText(img, "Label up: the small arrow (UP) in the left border points to the top edge.", (x0, int(1.5 * DPI)),
                    font, 0.75, 0, 2, cv2.LINE_AA)
        # id and "up" arrow INSIDE the cut card (in the outer part of the white border, at least
        # 0.25 in away from the black square, thin lines), so the cut-out tag still shows them
        cv2.putText(img, f"TAG {t.id}", (x0, y0 + px + bw - int(0.07 * DPI)), font, 0.7, 0, 2,
                    cv2.LINE_AA)
        ax = x0 - bw + int(0.13 * DPI)
        _arrow_up(img, ax, y0 + px // 2 - int(0.37 * DPI), y0 + px // 2 + int(0.37 * DPI), 3)
        cv2.putText(img, "UP", (x0 - bw + int(0.04 * DPI), y0 + px // 2 - int(0.43 * DPI)),
                    font, 0.55, 0, 2, cv2.LINE_AA)
        for i, line in enumerate(_HOW[t.kind]):
            cv2.putText(img, line, (x0, y0 + px + int((0.85 + 0.3 * i) * DPI)), font, 0.62, 0, 2,
                        cv2.LINE_AA)
        cv2.putText(img, f"Cut exactly on the dashed line ({CARD_BORDER_IN:g} in white border). "
                    "Measure the placement with a tape to 0.25 in.", (x0, y0 + px + int(1.5 * DPI)),
                    font, 0.62, 0, 2, cv2.LINE_AA)
        # print-scale check: a line as long as the tag, with end ticks
        ly = H - int(1.0 * DPI)
        cv2.line(img, (x0, ly), (x0 + px, ly), 0, 5)
        cv2.line(img, (x0, ly - 25), (x0, ly + 25), 0, 5)
        cv2.line(img, (x0 + px, ly - 25), (x0 + px, ly + 25), 0, 5)
        cv2.putText(img, f"This line must measure {size:.2f} in. Print at 100% / Actual size, "
                    "not fit to page.", (x0, ly + int(0.45 * DPI)), font, 0.7, 0, 2, cv2.LINE_AA)
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


def tag_sheet_pdf_bytes(size_in: float | None = None) -> bytes:
    return _build_pdf_pages(render_tag_pages(size_in), PAGE_IN)


def write_tag_sheet_pdf(path: str | Path, size_in: float | None = None) -> Path:
    """Write the printable tag sheet: one portrait letter page per tag (4 pages, ids
    100-103), each tag `size_in` (default 6.0 in) with its quiet zone, labeled with its frame
    feature, an "edge up" arrow, taping instructions and a ruler line of the tag's length for
    the print-scale check. Also writes page PNGs next to it (<stem>_p1.png, ...). Returns the
    PDF path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pages = render_tag_pages(size_in)
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

    If `alliance` and `state` (a field.HiveState) are given, the learned corners are compared
    with the computed ones (`hive_tag_corners_all`, both cells are CAD-pinned) and
    info["error_vs_computed_in"] = {id: worst corner error in inches}: a verification of
    the model on the real field, not an input to the solver.
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
        comp = hive_tag_corners_all(alliance, state)
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
def hive_tag_corners_all(alliance: str = "red", state=None) -> dict[int, np.ndarray]:
    """{id: (4,3)} computed (CAD-pinned) corners of the tags on BOTH cells of `alliance` in
    `state` (a field.HiveState, default audience up): `field.hive_tag_corners` per cell."""
    st = state or field.HiveState(alliance, "audience")
    out: dict[int, np.ndarray] = {}
    for which in field.CELLS:
        for k, v in field.hive_tag_corners(alliance, which, st).items():
            out[int(k)] = np.asarray(v, float).reshape(4, 3)
    return out


def up_cell_tag_corners(alliance: str = "red", which: str = "audience") -> dict[int, np.ndarray]:
    """{id: (4,3)} computed corners of the tags on the UP cell `which` of `alliance`
    (the state in which `which` is up): `field.hive_tag_corners(alliance, which, state)`."""
    got = field.hive_tag_corners(alliance, which, field.HiveState(alliance, which))
    return {int(k): np.asarray(v, float).reshape(4, 3) for k, v in got.items()}


def hive_tag_defs(alliance: str = "red", state=None, learned: dict | None = None
                  ) -> dict[int, np.ndarray]:
    """tag_defs for the HIVE tags of `alliance` in `state` (a field.HiveState, default audience
    up): the computed, CAD-pinned corners of BOTH cells (`field.hive_tag_corners`), plus any
    `learned` tags of ids that have no computed position (e.g. the other alliance's); on a
    clash the computed value wins (learning is a verification, not an input)."""
    out = hive_tag_defs_from_learned(learned or {})
    out.update(hive_tag_corners_all(alliance, state))
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

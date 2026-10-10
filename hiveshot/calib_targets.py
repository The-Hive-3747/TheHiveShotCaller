"""Printable calibration targets and the field-point reference sheet."""

from __future__ import annotations

import zlib
from pathlib import Path

import cv2
import numpy as np

from hiveshot import field
from hiveshot import field_constants as fc

DPI = 300
LETTER_LANDSCAPE_IN = (11.0, 8.5)
A4_LANDSCAPE_IN = (11.69, 8.27)
MARGIN_IN = 0.4


def render_checkerboard(
    cols: int = 10, rows: int = 7, square_in: float = 1.0
) -> tuple[np.ndarray, tuple[float, float]]:
    """Render the board on a landscape page at 300 dpi.

    Returns (gray uint8 image, (page_w_in, page_h_in)). Top-left square is
    black. Letter is used if the board plus margins fits, else A4.
    """
    bw, bh = cols * square_in, rows * square_in
    page = None
    for cand in (LETTER_LANDSCAPE_IN, A4_LANDSCAPE_IN):
        if bw + 2 * MARGIN_IN <= cand[0] and bh + 2 * MARGIN_IN + 0.5 <= cand[1]:
            page = cand
            break
    if page is None:
        raise ValueError(
            f"{cols}x{rows} board of {square_in} in squares does not fit on letter or A4 landscape"
        )
    W, H = int(round(page[0] * DPI)), int(round(page[1] * DPI))
    img = np.full((H, W), 255, np.uint8)
    sq = square_in * DPI
    x0 = int(round((W - bw * DPI) / 2))
    y0 = int(round((H - 0.5 * DPI - bh * DPI) / 2))
    for r in range(rows):
        for c in range(cols):
            if (r + c) % 2 == 0:
                xa, xb = x0 + int(round(c * sq)), x0 + int(round((c + 1) * sq))
                ya, yb = y0 + int(round(r * sq)), y0 + int(round((r + 1) * sq))
                img[ya:yb, xa:xb] = 0
    text = (
        f"Calibration checkerboard {cols}x{rows} squares ({cols - 1}x{rows - 1} inner corners). "
        f"Square = {square_in:g} in. Print at 100% / Actual size - verify with a ruler."
    )
    cv2.putText(img, text, (x0, H - int(0.3 * DPI)), cv2.FONT_HERSHEY_SIMPLEX, 0.9, 0, 2, cv2.LINE_AA)
    return img, page


def _build_pdf(gray: np.ndarray, page_in: tuple[float, float]) -> bytes:
    """Hand-written single-page PDF embedding the gray image full-page."""
    h, w = gray.shape
    pw, ph = page_in[0] * 72.0, page_in[1] * 72.0
    stream = zlib.compress(gray.tobytes(), 9)
    content = f"q {pw:.3f} 0 0 {ph:.3f} 0 0 cm /Im0 Do Q".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {pw:.3f} {ph:.3f}] "
            "/Resources << /XObject << /Im0 5 0 R >> >> /Contents 4 0 R >>"
        ).encode(),
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        (
            f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} "
            f"/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode "
            f"/Length {len(stream)} >>\nstream\n"
        ).encode()
        + stream
        + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def write_checkerboard_pdf(
    path: str | Path, cols: int = 10, rows: int = 7, square_in: float = 1.0
) -> Path:
    """Write the checkerboard PDF at `path` and a PNG next to it (same stem).

    10x7 squares = 9x6 inner corners. Returns the PNG path.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    img, page = render_checkerboard(cols, rows, square_in)
    path.write_bytes(_build_pdf(img, page))
    png = path.with_suffix(".png")
    cv2.imwrite(str(png), img)
    return png


CELL_CORNER_NAMES = ("high-left", "high-right", "low-right", "low-left")
# "left"/"right" refer to the field X axis: left = the -X side of the opening, right = +X.
# (Seen from the recommended tripod spots the -X side appears on the image RIGHT.)
CELL_NAME_PREFIX = "Red HIVE up-CELL opening, "
FRAME_TOP_NAMES = (
    "HIVE frame top corner (-X, +Y)",
    "HIVE frame top corner (+X, +Y)",
    "HIVE frame top corner (-X, -Y)",
    "HIVE frame top corner (+X, -Y)",
)
# polygon order in field.cell_opening_polygon is low-left, low-right, high-right, high-left
_POLY_INDEX = {"high-left": 3, "high-right": 2, "low-right": 1, "low-left": 0}


def up_cell_opening_corners(alliance: str = "red", which: str = "audience"
                            ) -> list[tuple[float, float, float]]:
    """Corners of the opening of the UP cell `which` of `alliance`, field frame, inches.

    No independent derivation: this is hiveshot.field.cell_opening_polygon (the model
    used for scoring, the viewer and camera placement). Order: high-left, high-right,
    low-right, low-left (left = -X side).
    """
    poly = field.cell_opening_polygon(alliance, which, field.HiveState(alliance, which))
    return [tuple(float(v) for v in poly[_POLY_INDEX[n]]) for n in CELL_CORNER_NAMES]


def frame_top_corners() -> list[tuple[float, float, float]]:
    """Top corners of the HIVE frame box, order of FRAME_TOP_NAMES.

    Taken from field.hive_frame_wireframe(): the audience-side top bar is the segment
    from (-FRAME_WIDTH_X/2, +FRAME_DEPTH_Y/2, FRAME_TOP_Z) to
    (+FRAME_WIDTH_X/2, +FRAME_DEPTH_Y/2, FRAME_TOP_Z); the far-side top bar is the same
    with -FRAME_DEPTH_Y/2. Looked up in the wireframe so the numbers cannot drift.
    """
    segs = field.hive_frame_wireframe()
    top = [s for s in segs
           if abs(s[0][2] - field.FRAME_TOP_Z) < 1e-9 and abs(s[1][2] - field.FRAME_TOP_Z) < 1e-9
           and abs(abs(s[0][1]) - fc.FRAME_DEPTH_Y / 2) < 1e-9
           and abs(s[0][1] - s[1][1]) < 1e-9 and abs(abs(s[0][0]) - fc.FRAME_WIDTH_X / 2) < 1e-9]
    bars = {}
    for a, b in top:
        lo, hi = (a, b) if a[0] < b[0] else (b, a)
        bars[1 if a[1] > 0 else -1] = (tuple(float(v) for v in lo), tuple(float(v) for v in hi))
    return [bars[1][0], bars[1][1], bars[-1][0], bars[-1][1]]


def field_reference_points() -> list[tuple[str, tuple[float, float, float]]]:
    """The 8 points to click, in click order. All are in the air on the HIVE, because from
    the recommended tripod spots (aim z=61 in) the floor is out of frame."""
    pts: list[tuple[str, tuple[float, float, float]]] = []
    for n, p in zip(CELL_CORNER_NAMES, up_cell_opening_corners(), strict=True):
        pts.append((CELL_NAME_PREFIX + n + " corner", p))
    for n, p in zip(FRAME_TOP_NAMES, frame_top_corners(), strict=True):
        pts.append((n, p))
    return pts


def reference_point_names() -> list[str]:
    """Names of the 8 reference points in click order (what the UI and API use)."""
    return [n for n, _ in field_reference_points()]


def write_field_point_sheet(path: str | Path) -> Path:
    """Write markdown listing 8 field-frame reference points to click."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pts = field_reference_points()
    rows = "\n".join(
        f"| {i} | {name} | {x:.2f} | {y:.2f} | {z:.2f} |"
        for i, (name, (x, y, z)) in enumerate(pts, 1)
    )
    cell = [p for _, p in pts[:4]]
    ys = sorted({round(p[1], 2) for p in cell})
    zs = sorted({round(p[2], 2) for p in cell})
    text = f"""# Field reference points for extrinsic calibration

All coordinates are inches in the field frame: origin at field center on the tile
surface, Z up, **+Y toward the audience side (the audience-side CELL)**, X along the
red/blue axis (red HIVE at X = {fc.RED_HIVE_X}, blue HIVE at X = {fc.BLUE_HIVE_X}).
**VERIFY every row against the official CAD / a tape measure before trusting it.**
Click the same physical point in each camera, in this order.

| # | Point | X | Y | Z |
|---|-------|---|---|---|
{rows}

"left" / "right" in the CELL names mean the -X / +X side of the opening. "high" is the
upper edge of the tilted opening, "low" the lower edge.

## Derivation (VERIFY)

- Points 1-4, up-CELL opening corners: taken directly from
  `hiveshot.field.cell_opening_polygon("red", "audience", HiveState("red", "audience"))`,
  the same model used for scoring and the 3-D viewer. The opening is
  {fc.CELL_OPENING_WIDTH} in wide (X) by {fc.CELL_OPENING_HEIGHT} in tall in its own plane,
  centered at y = {field.OPENING_CENTER_ABS_Y:.2f} (OPENING_CENTER_ABS_Y), z = {fc.UP_CELL_OPENING_CENTER_Z},
  plane {fc.OPENING_PLANE_FROM_HORIZONTAL_DEG} deg from horizontal. Corner y values
  {ys}, z values {zs}.
- Points 5-8, HIVE frame top corners: the corners of the two horizontal top bars of the
  frame box in `field.hive_frame_wireframe()`. Audience-side bar (points 5, 6): from
  (-{fc.FRAME_WIDTH_X / 2:.2f}, +{fc.FRAME_DEPTH_Y / 2:.2f}, {field.FRAME_TOP_Z:.2f}) to
  (+{fc.FRAME_WIDTH_X / 2:.2f}, +{fc.FRAME_DEPTH_Y / 2:.2f}, {field.FRAME_TOP_Z:.2f}). Far-side
  bar (points 7, 8): the same with Y = -{fc.FRAME_DEPTH_Y / 2:.2f}. FRAME_TOP_Z
  (= PIVOT_HEIGHT + 20) is an ASSUMED frame height and FRAME_WIDTH_X / FRAME_DEPTH_Y are
  VERIFY: tape-measure the real top corners and correct field.py / field_constants.py.
- Red HIVE X = {fc.RED_HIVE_X} (HIVE_CENTER_SPACING_X / 2, VERIFY). The sheet assumes the
  audience-side CELL is the up CELL. Set the HIVE that way before calibrating.
- Floor features (tile seams, frame base corners) are NOT used: from the recommended
  camera poses (aimed at z = 61 in) the floor is outside the image.
"""
    path.write_text(text, encoding="utf-8")
    return path

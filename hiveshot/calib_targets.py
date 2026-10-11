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
# "high" = the upper edge of the tilted opening (z 65.6 in), "low" = the lower edge (53.5 in).
# (Seen from the recommended tripod spots the -X side appears on the image RIGHT.)
RED_CELL_PREFIX = "Red HIVE up-CELL opening, "
BLUE_CELL_PREFIX = "Blue HIVE far-CELL opening, "
CELL_NAME_PREFIX = RED_CELL_PREFIX         # kept for callers of the old name
# Match-start state (Field Setup Guide 11.1): red HIVE audience CELL up, blue HIVE far CELL up.
# The 8 click points are the corners of these two physically real openings.
CALIB_HIVE_STATES = (("red", "audience"), ("blue", "far"))
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


def field_reference_points() -> list[tuple[str, tuple[float, float, float]]]:
    """The 8 points to click, in click order: the four corners of the red HIVE's audience
    CELL opening (up at match start) and the four corners of the blue HIVE's far CELL opening
    (also up at match start). All are physical corners of the CELL openings, in the air on
    the HIVE (from the recommended tripod spots the floor is out of frame)."""
    pts: list[tuple[str, tuple[float, float, float]]] = []
    for prefix, (alliance, which) in zip((RED_CELL_PREFIX, BLUE_CELL_PREFIX), CALIB_HIVE_STATES,
                                         strict=True):
        for n, p in zip(CELL_CORNER_NAMES, up_cell_opening_corners(alliance, which), strict=True):
            pts.append((prefix + n + " corner", p))
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
    text = f"""# Field reference points for extrinsic calibration

All coordinates are inches in the field frame: origin at field center on the tile
surface, Z up, **+Y toward the audience side (the audience-side CELL)**, X along the
red/blue axis (red HIVE at X = {fc.RED_HIVE_X}, blue HIVE at X = {fc.BLUE_HIVE_X}).
Click the same physical point in each camera, in this order. Set the HIVE to the match-start
state first: red HIVE audience CELL up, blue HIVE far CELL up.

| # | Point | X | Y | Z |
|---|-------|---|---|---|
{rows}

"left" / "right" in the names mean the -X / +X side of the opening. "high" is the upper edge
of the tilted opening, "low" the lower edge (for the far CELL the high edge is the one nearer
the pivot).

## Derivation

- Points 1-4: the corners of the red HIVE's audience-CELL opening, points 5-8: the corners
  of the blue HIVE's far-CELL opening, both taken directly from
  `hiveshot.field.cell_opening_polygon(alliance, which, HiveState(alliance, which))` (the model
  used for scoring and the 3-D viewer, which follows the official CAD). Each opening is
  {fc.CELL_OPENING_WIDTH} in wide (X) by {fc.CELL_OPENING_HEIGHT} in tall in its own plane,
  plane {fc.OPENING_PLANE_FROM_HORIZONTAL_DEG} deg from horizontal, spanning z
  {fc.UP_CELL_OPENING_Z_RANGE[0]} to {fc.UP_CELL_OPENING_Z_RANGE[1]} in (official figure 9-9).
- The openings of the blue far CELL face away from the audience: from the camera spots you see
  its rim from behind. Click the corners of the opening rim (the corners of the 20 x 14 in
  opening, where the CELL walls end), not the corners of the CELL body behind it.
- Points are real physical corners; the earlier frame "top corners" do not exist on the CAD A-frame
  and are no longer used. Floor features (tile seams, frame base corners) are not used either:
  from the recommended camera poses the floor is outside the image.
"""
    path.write_text(text, encoding="utf-8")
    return path

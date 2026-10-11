"""Documentation figure of the printed kit: docs/kit_tag_positions.png / .svg.

Everything is drawn from the field model (`hiveshot.field`, `hiveshot.field_constants`) and the kit
definition (`hiveshot.tagkit`), in the calibration state (`field.CALIBRATION_STATE`: both audience
CELLs up). Three panels: a side view (looking along +X, so +Y, the audience, is on the left), a
front view (from the audience, looking along -Y, so +X, the red HIVE, is on the left) and a
detail of the base tag with its card border and foam wedge. The PNG is drawn with cv2, the SVG
from the same primitive list, so both files are byte-for-byte reproducible (`write_kit_figure`).
"""
from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np

from . import field, tagkit
from . import field_constants as C

W, H = 3500, 1500
BG, INK, GRID = "#ffffff", "#202020", "#d8d8d8"
FRAME, PANEL, TAGC = "#707070", "#c8d6e8", "#101010"
RED, BLUE = "#d02020", "#2040d0"
FONT = cv2.FONT_HERSHEY_SIMPLEX


def _bgr(h: str):
    return (int(h[5:7], 16), int(h[3:5], 16), int(h[1:3], 16))


class _Canvas:
    """Collects primitives; `png()` rasterizes them with cv2, `svg()` writes the same list."""

    def __init__(self):
        self.p = []

    def line(self, a, b, color=INK, w=2, dash=False):
        self.p.append(("line", a, b, color, w, dash))

    def poly(self, pts, fill=None, stroke=INK, w=2, dash=False):
        self.p.append(("poly", [tuple(map(float, q)) for q in pts], fill, stroke, w, dash))

    def text(self, x, y, s, scale=0.8, color=INK, bold=False):
        self.p.append(("text", float(x), float(y), s, scale, color, bold))

    def png(self):
        img = np.full((H, W, 3), 255, np.uint8)
        for q in self.p:
            if q[0] == "line":
                _, a, b, col, w, dash = q
                for s, e in (_dashes(a, b) if dash else [(a, b)]):
                    cv2.line(img, _pt(s), _pt(e), _bgr(col), int(w), cv2.LINE_AA)
            elif q[0] == "poly":
                _, pts, fill, stroke, w, dash = q
                arr = np.array([_pt(t) for t in pts], np.int32)
                if fill:
                    cv2.fillPoly(img, [arr], _bgr(fill), cv2.LINE_AA)
                if stroke:
                    for i in range(len(pts)):
                        a, b = pts[i], pts[(i + 1) % len(pts)]
                        for s, e in (_dashes(a, b) if dash else [(a, b)]):
                            cv2.line(img, _pt(s), _pt(e), _bgr(stroke), int(w), cv2.LINE_AA)
            else:
                _, x, y, s, scale, col, bold = q
                cv2.putText(img, s, (int(round(x)), int(round(y))), FONT, scale, _bgr(col),
                            2 if bold else 1, cv2.LINE_AA)
        return img

    def svg(self):
        o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
             f'viewBox="0 0 {W} {H}" font-family="Arial, sans-serif">',
             f'<rect width="{W}" height="{H}" fill="{BG}"/>']
        for q in self.p:
            if q[0] == "line":
                _, a, b, col, w, dash = q
                o.append(f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" '
                         f'stroke="{col}" stroke-width="{w}" stroke-linecap="round"'
                         + (' stroke-dasharray="10 8"' if dash else "") + "/>")
            elif q[0] == "poly":
                _, pts, fill, stroke, w, dash = q
                pp = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
                o.append(f'<polygon points="{pp}" fill="{fill or "none"}" '
                         f'stroke="{stroke or "none"}" stroke-width="{w}" stroke-linejoin="round"'
                         + (' stroke-dasharray="10 8"' if dash else "") + "/>")
            else:
                _, x, y, s, scale, col, bold = q
                s = s.replace("&", "&amp;").replace("<", "&lt;")
                o.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{round(scale * 29)}" fill="{col}"'
                         + (' font-weight="bold"' if bold else "") + f">{s}</text>")
        o.append("</svg>")
        return "\n".join(o) + "\n"


def _pt(p):
    return (int(round(p[0])), int(round(p[1])))


def _dashes(a, b, on=10.0, off=8.0):
    d = np.subtract(b, a, dtype=float)
    n = float(np.hypot(*d))
    if n == 0:
        return []
    u = d / n
    out, t = [], 0.0
    while t < n:
        out.append((tuple(np.add(a, u * t)), tuple(np.add(a, u * min(t + on, n)))))
        t += on + off
    return out


def _hull(pts2):
    h = cv2.convexHull(np.array(pts2, np.float32)).reshape(-1, 2)
    return [tuple(p) for p in h]


class _View:
    """Maps two field axes to the canvas: horizontal axis `h` (sign `sgn`), vertical axis z."""

    def __init__(self, axis, sgn, scale, ox, oy):
        self.axis, self.sgn, self.s, self.ox, self.oy = axis, sgn, scale, ox, oy

    def __call__(self, p):
        p = np.asarray(p, float)
        return (self.ox + self.sgn * p[self.axis] * self.s, self.oy - p[2] * self.s)

    def hz(self, hval, z):
        return (self.ox + self.sgn * hval * self.s, self.oy - z * self.s)


def _dim(cv, a, b, label, off=(0, 0), scale=0.6, color="#a02080"):
    """Dimension line a-b with end ticks and a label placed at the middle plus `off`."""
    cv.line(a, b, color, 2)
    d = np.subtract(b, a, dtype=float)
    n = np.array([-d[1], d[0]]) / (np.hypot(*d) or 1.0) * 7
    for q in (a, b):
        cv.line(tuple(np.add(q, n)), tuple(np.subtract(q, n)), color, 2)
    cv.text((a[0] + b[0]) / 2 + off[0], (a[1] + b[1]) / 2 + off[1], label, scale, color)


def _frame_geometry(cv, view, side):
    """Frame (legs, crossbar, pivot cradles), foot bars, logo panels in `view`."""
    h = C.FRAME_BASE_HALF_Y
    xo, xi = C.FRAME_BASE_X_OUTER, C.FRAME_BASE_X_INNER
    bh = C.FRAME_BASE_HEIGHT
    for sx in (-1, 1):
        if side:     # side view: the foot bar spans y -h..h, z 0..bh (one bar seen end-on)
            if sx == 1:
                cv.poly([view.hz(-h, 0), view.hz(h, 0), view.hz(h, bh), view.hz(-h, bh)],
                        "#b0b0b0", FRAME, 2)
        else:
            cv.poly([view.hz(sx * xi, 0), view.hz(sx * xo, 0), view.hz(sx * xo, bh),
                     view.hz(sx * xi, bh)], "#b0b0b0", FRAME, 2)
    for a, b in field._frame_segments():
        if np.allclose(a[2], 0) and np.allclose(b[2], 0):
            continue                                   # foot-bar footprint (drawn above)
        cv.line(view(a), view(b), FRAME, 3)
    for sidename in ("audience", "far"):
        q, _ = field.logo_panel_face(sidename)
        cv.poly([view(p) for p in q], PANEL if sidename == "audience" else None, "#4060a0", 2,
                dash=sidename == "far")


def _cells(cv, view, side):
    st = field.CALIBRATION_STATE
    for al, which, corners in field.all_cell_bodies(st):
        col = RED if al == "red" else BLUE
        up = which == st[al].up_cell
        pts = [view(p) for p in corners]
        cv.poly(_hull(pts), None, col, 3 if up else 2, dash=not up)


def _tags(cv, view, side):
    for t in tagkit.KIT_TAGS:
        c = tagkit.tag_corners_xyz(t.id)
        if side:
            cv.line(view(c[0]), view(c[3]), TAGC, 8)          # edge-on: the tag is a line
        else:
            cv.poly([view(p) for p in c], "#303030", TAGC, 2)
            ctr = np.mean([view(p) for p in c], axis=0)
            cv.text(ctr[0] - 16, ctr[1] + 8, str(t.id), 0.9, "#ffffff", True)


def _axes(cv, view, hrange, zmax, label):
    for hv in range(hrange[0], hrange[1] + 1, 12):
        a = view.hz(hv, 0)
        cv.line(a, view.hz(hv, zmax), GRID, 1)
        cv.text(a[0] - 14, a[1] + 26, f"{hv:g}", 0.55, "#808080")
    for z in range(0, int(zmax) + 1, 12):
        e = view.hz(hrange[0], z)
        cv.line(view.hz(hrange[1], z), e, GRID, 1)
        cv.text(e[0] + 8, e[1] + 5, f"z {z}", 0.55, "#808080")
    cv.line(view.hz(hrange[0], 0), view.hz(hrange[1], 0), INK, 4)      # tiles
    mid = view.hz(0, 0)
    cv.text(mid[0] - 60, mid[1] + 56, label, 0.6, "#808080")


def _note(cv, x, y, lines, color=INK, head=True, step=24):
    for i, ln in enumerate(lines):
        cv.text(x, y + i * step, ln, 0.62 if (i == 0 and head) else 0.55, color, i == 0 and head)


def _side(cv):
    v = _View(1, -1, 14.0, 560.0, 1270.0)
    cv.text(40, 120, "SIDE VIEW (looking along +X; the audience, +Y, is on the LEFT)", 0.95, INK, True)
    _axes(cv, v, (-36, 36), 72, "tiles, y (in)")
    _frame_geometry(cv, v, True)
    _cells(cv, v, True)
    _tags(cv, v, True)
    c100 = tagkit.tag_center_xyz(100)
    px, py = v.hz(c100[1], c100[2])
    _note(cv, 640, 170, ["tags 100 + 101: flat on the logo panel (edge-on here)",
                         "centers (x -10 / +10, y 2.89, z 37.28)",
                         "top edge flush with the panel top (y 1.67, z 40.02)"])
    cv.line((px - 4, py - 6), (636, 164), INK, 1)
    ocx = field.cell_opening_plane("red", "audience", field.CALIBRATION_STATE["red"])[0]
    ox_, oy_ = v.hz(ocx[1], ocx[2])
    _note(cv, 40, 190, ["audience up-CELLs (red x +12.75, blue x -12.75)",
                        f"opening center (+-12.75, {ocx[1]:.2f}, {ocx[2]:.2f}), tag rows z 49.8"], color=INK)
    cv.line((ox_ - 6, oy_ - 6), (150, 214), INK, 1)
    fx, fy = v.hz(-20, 50)
    cv.text(fx - 120, fy - 70, "far CELLs (down, dashed)", 0.55, "#606060")
    x0, y0 = v.hz(26, 9)
    x1, y1 = v.hz(15.5, -1.5)
    cv.poly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], None, "#a02080", 2, dash=True)
    cv.text(x0 + 4, y0 - 12, "base tag 102 / 103: detail at right", 0.6, "#a02080", True)
    cv.text(40, 1440, "Frame: foot bar (gray) y -19.47..+19.47, 2.15 in high; legs to the 24 in crossbar (z 41.45); the logo panel", 0.55, "#404040")
    cv.text(40, 1466, "leans 24 deg (blue line). Red and blue HIVEs overlap in this view.", 0.55, "#404040")


def _front(cv):
    S = 13.0
    v = _View(0, -1, S, 1840.0, 1270.0)
    cv.text(1180, 120, "FRONT VIEW (from the audience, looking along -Y; +X, red, is on the LEFT)", 0.95, INK, True)
    _axes(cv, v, (-48, 48), 72, "tiles, x (in)")
    _frame_geometry(cv, v, False)
    _cells(cv, v, False)
    _tags(cv, v, False)
    _note(cv, 1230, 175, ["red up-CELL (x 2.75..22.75)"], RED)
    _note(cv, 2170, 175, ["blue up-CELL (x -22.75..-2.75)"], BLUE)
    _note(cv, 1740, 175, ["tags 100 / 101: 6 in squares on the panel", "centers x -/+10.0, z 37.28 (on the slope),",
                          "outer edge 0.22 in inside the panel corner"])
    b3 = tagkit.tag_center_xyz(103)
    bx, by = v.hz(b3[0], b3[2])
    _note(cv, 1190, 1355, ["103 (+X base corner)", "center (21.73, 19.06, 3.29)",
                           "black square x 18.73..24.73 (flush with the", "foot bar outer face), z 0.47..6.11",
                           "foam wedge behind the card, inboard: x 18.73..22.75"])
    cv.line((bx, by + 30), (bx, 1340), INK, 1)
    b2 = tagkit.tag_center_xyz(102)
    bx2, by2 = v.hz(b2[0], b2[2])
    _note(cv, 2060, 1355, ["102 (-X base corner)", "center (-21.73, 19.06, 3.29)",
                           "black square x -24.73..-18.73, z 0.47..6.11",
                           "foam wedge behind the card, inboard: x -18.73..-22.75"])
    cv.line((bx2, by2 + 30), (bx2, 1340), INK, 1)
    cv.text(1180, 1466, "Both audience CELLs are up (calibration state): tip BOTH HIVEs by hand before calibrating. "
            "Black squares are the kit tags (to scale); dashed outlines are the CELLs that point away.", 0.55, "#404040")


def _detail(cv):
    S = 80.0
    ox, oy = 4408.0, 800.0

    def P(y, z):
        return (ox - y * S, oy - z * S)

    t20 = math.radians(tagkit.BASE_TILT_DEG)
    bw = tagkit.CARD_BORDER_IN
    size = tagkit.DEFAULT_TAG_SIZE_IN
    hb = C.FRAME_BASE_HALF_Y
    yb = hb + C.FRAME_BASE_HEIGHT * math.tan(t20)                     # card bottom edge on the tile
    u = np.array([-math.sin(t20), math.cos(t20)])                     # up the card (y, z)
    n = np.array([math.cos(t20), math.sin(t20)])                      # face normal (y, z)
    cv.text(2560, 120, "BASE TAG DETAIL (side view, tag 102 / 103)", 0.95, INK, True)
    cv.line(P(16.2, 0), P(22.6, 0), INK, 4)
    for yy in (17, 19, 21):
        cv.text(P(yy, 0)[0] - 12, P(yy, 0)[1] + 26, str(yy), 0.55, "#808080")
    cv.poly([P(16.2, 0), P(hb, 0), P(hb, C.FRAME_BASE_HEIGHT), P(16.2, C.FRAME_BASE_HEIGHT)],
            "#b0b0b0", FRAME, 2)
    cv.text(P(18.0, 2.15)[0], P(18.0, 2.15)[1] - 12, "foot bar end (2.15 in high)", 0.5, "#404040")
    w, d, h = tagkit.STAND_WEDGE_IN
    cv.poly([P(yb, 0), P(yb - d, 0), P(yb - d, h)], "#f0e0b0", "#a07030", 2)

    def along(s, off=0.0):
        a = np.array([yb, 0.0]) + u * s + n * off
        return P(a[0], a[1])
    s1, s2, s3 = bw, bw + size, 2 * bw + size
    cv.poly([along(0), along(s3), along(s3, 0.18), along(0, 0.18)], "#ffffff", "#404040", 2)
    cv.poly([along(s1), along(s2), along(s2, 0.18), along(s1, 0.18)], TAGC, TAGC, 2)
    z_bot = bw * math.cos(t20)
    cv.line(P(23.0, z_bot), along(s1, 0.18), "#a02080", 1, True)
    cv.line(P(23.0, 0), P(yb + 0.3, 0), "#a02080", 1, True)
    _dim(cv, P(23.0, 0), P(23.0, z_bot), "", (0, 0))
    cv.text(P(23.0, 0)[0] + 14, P(23.0, 0)[1] - 10, f"{z_bot:.2f} in", 0.6, "#a02080", True)
    cv.text(P(23.0, 0)[0] - 30, P(23.0, 0)[1] - 44, "black-square bottom", 0.5, "#a02080")
    _dim(cv, P(yb, -0.6), P(hb, -0.6), "", (0, 0))
    cv.text(P(yb, -0.6)[0] - 4, P(yb, -0.6)[1] + 26, f"{yb - hb:.2f} in", 0.55, "#a02080")
    _dim(cv, P(yb, -1.4), P(yb - d, -1.4), "", (0, 0))
    cv.text(P(yb - d, -1.4)[0] + 22, P(yb - d, -1.4)[1] + 8, f"{d:g} in deep", 0.55, "#805010")
    top = np.array([yb, 0.0]) + u * s2
    tpx = P(top[0], top[1])
    _note(cv, 2560, 190, [f"black square top edge: y {top[0]:.2f}, z {top[1]:.2f}",
                          "(tag leans back 20 deg from vertical)"], head=False)
    cv.line((tpx[0], tpx[1] - 6), (2900, 218), INK, 1)
    wt = P(yb - d, h)
    _note(cv, wt[0] + 40, wt[1] - 10, [f"foam wedge {w:g} wide x {d:g} deep x {h:g} tall",
                                       f"({d:g} / {h:g} = tan 20 deg)"], "#805010", step=22)
    cv.line((wt[0] + 4, wt[1]), (wt[0] + 36, wt[1] - 14), "#805010", 1)
    _note(cv, 2560, 1090, [
        "Card = 6.00 in black square + 0.5 in white border (cut on the dashed line).",
        f"Card bottom edge on the tile at y = {hb:g} + {C.FRAME_BASE_HEIGHT:g} tan 20 deg = {yb:.2f}",
        "(0.78 in beyond the foot bar end); the card rests on the foot bar end's top edge.",
        f"Black-square bottom edge height = 0.5 x cos 20 deg = {z_bot:.2f} in; top edge z {top[1]:.2f}.",
        "Black square outer edge flush with the foot bar's outer face (x = +-24.73).",
        "Wedge position along the card: INBOARD, x 18.73..22.75 (|x|), on the tile beside the foot bar (the bar is only",
        "x 22.75..24.73), so it clears the bar; the card's outer 2 in rests on the bar end. Only the card position counts."],
        head=False, step=26)


def _build() -> _Canvas:
    cv = _Canvas()
    cv.text(40, 60, "Kit tag positions on the HIVE frame (calibration state: both audience CELLs up). Inches, field frame:"
            " origin field center on the tiles, Z up, +Y toward the audience.", 0.8, INK, True)
    _side(cv)
    _front(cv)
    _detail(cv)
    return cv


def write_kit_figure(png_path, svg_path) -> None:
    """Write docs/kit_tag_positions.png (cv2) and .svg from the field model."""
    cv = _build()
    Path(svg_path).write_text(cv.svg(), encoding="utf-8")
    cv2.imwrite(str(png_path), cv.png())

"""Diagrams for docs/builder_setup.md: the field map as a builder sees it, and the wiring.

Run:  .venv\\Scripts\\python.exe tools\\make_builder_diagrams.py [--png]
Writes docs/builder_field_map.svg and docs/builder_wiring.svg. With --png it also renders
both to PNG with a headless Edge or Chrome (whichever is installed), for people who open
the docs without a Markdown viewer.

The camera spots, lens heights, tape distances and aim points come from
placement.recommend("usb") and placement.operator_measurements(), the same source as
docs/camera_placement.md, so the map follows the optimizer. tests/test_placement.py checks
that the committed SVG and builder_setup.md still carry the optimizer's numbers.

The map is drawn the way you see the field standing OUTSIDE the audience wall and looking
in: the audience (+Y) is at the bottom of the page and the red HIVE (+X) is on the LEFT.
That is mirrored against docs/camera_placement.png, which has +X on the right.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hiveshot import field as F  # noqa: E402
from hiveshot import placement as P  # noqa: E402

DOCS = ROOT / "docs"

# ------------------------------------------------------------------ parts (PURCHASE_LIST.md)
CAMERA_CABLE = "camera's own USB cable (about 3 ft)"
EXTENSION = "active USB 3.0 extension, 16.4 ft"
TRIPOD_LEG_RADIUS_IN = 20.0  # assumed foot-to-centre distance (camera_placement.md, VERIFY)

# ------------------------------------------------------------------ map layout (px)
W, H = 1240, 1250
S = 5.0  # px per inch
CX, CY = 620.0, 500.0  # field centre on the page
COL = {"A": "#1a5fd0", "B": "#1e8a2e"}
RED, BLUE, INK, GREY = "#d02020", "#2040d0", "#111111", "#666666"
FONT = "font-family='Segoe UI, Arial, Helvetica, sans-serif'"


def sx(x: float) -> float:
    """Field x (inches, +X = red) to page x: +X is on the LEFT for someone at the audience wall."""
    return CX - x * S


def sy(y: float) -> float:
    """Field y (inches, +Y = audience) to page y: the audience is at the bottom."""
    return CY + y * S


def _t(x, y, text, size=15, fill=INK, anchor="start", weight="normal", extra=""):
    return (f"<text x='{x:.1f}' y='{y:.1f}' font-size='{size}' fill='{fill}' "
            f"text-anchor='{anchor}' font-weight='{weight}' {FONT} {extra}>{text}</text>")


def _line(x1, y1, x2, y2, stroke=INK, width=2.0, extra=""):
    return (f"<line x1='{x1:.1f}' y1='{y1:.1f}' x2='{x2:.1f}' y2='{y2:.1f}' "
            f"stroke='{stroke}' stroke-width='{width}' {extra}/>")


def _dim_h(x1, x2, y, label, col):
    """Horizontal dimension line with end ticks and a label above it."""
    return "".join([
        _line(x1, y, x2, y, col, 1.6), _line(x1, y - 7, x1, y + 7, col, 1.6),
        _line(x2, y - 7, x2, y + 7, col, 1.6),
        _t((x1 + x2) / 2, y - 8, label, 14, col, "middle", "bold")])


def _dim_v(x, y1, y2, label, col, side=1):
    """Vertical dimension line with end ticks; label on the right (side=1) or left (-1)."""
    return "".join([
        _line(x, y1, x, y2, col, 1.6), _line(x - 7, y1, x + 7, y1, col, 1.6),
        _line(x - 7, y2, x + 7, y2, col, 1.6),
        _t(x + 10 * side, (y1 + y2) / 2 + 5, label, 14, col, "start" if side > 0 else "end",
           "bold")])


def builder_numbers() -> dict:
    """Everything the builder guide quotes, from the optimizer (Arducam option)."""
    rec = P.recommend("usb")
    out = {}
    for k in ("A", "B"):
        c = rec["cameras"][k]
        m = P.operator_measurements(c["pos"])
        yaw, pitch = P.aim_angles(c)
        out[k] = {
            "pos": tuple(float(v) for v in c["pos"]),
            "aim": tuple(float(v) for v in c["look_at"]),
            "lens_height_in": float(c["pos"][2]),
            "out_in": float(m["out_from_outer_face_in"]),
            "along_in": float(m["along_from_outer_edge_in"]),
            "corner": m["corner"],
            "yaw_deg": yaw, "pitch_deg": pitch,
        }
    return out


def field_map_svg(n: dict | None = None) -> str:
    n = n or builder_numbers()
    h = P.WALL_HALF
    wt = P.WALL_THICKNESS_IN * S
    o: list[str] = [
        f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {W} {H}' width='{W}' "
        f"height='{H}'>",
        f"<rect width='{W}' height='{H}' fill='#ffffff'/>",
        _t(30, 42, "Where everything goes: field map for builders", 26, INK, "start", "bold"),
        _t(30, 68, "Drawn as you see it standing outside the AUDIENCE wall, looking into the "
           "field. The RED HIVE is on your LEFT.", 15),
        _t(30, 90, "Floor tiles are 24 in. All tape distances are from the OUTSIDE of the "
           "field wall. Two cameras, two cables, one PC.", 15),
    ]
    # field floor, tile seams, wall
    x0, x1, y0, y1 = sx(h), sx(-h), sy(-h), sy(h)
    o.append(f"<rect x='{x0:.1f}' y='{y0:.1f}' width='{x1 - x0:.1f}' height='{y1 - y0:.1f}' "
             f"fill='#ececec'/>")
    for i in range(-2, 3):
        o.append(_line(sx(i * 24), y0, sx(i * 24), y1, "#b5b5b5", 1.2))
        o.append(_line(x0, sy(i * 24), x1, sy(i * 24), "#b5b5b5", 1.2))
    o.append(f"<rect x='{x0 - wt / 2:.1f}' y='{y0 - wt / 2:.1f}' width='{x1 - x0 + wt:.1f}' "
             f"height='{y1 - y0 + wt:.1f}' fill='none' stroke='{INK}' stroke-width='{wt:.1f}'/>")
    o.append(_t(CX, y0 - 16, "FAR SIDE", 15, GREY, "middle", "bold"))
    o.append(_t(x0 - 26, CY, "RED side (+X)", 17, RED, "middle", "bold",
                f"transform='rotate(-90 {x0 - 26:.1f} {CY:.1f})'"))
    o.append(_t(x1 + 38, CY, "BLUE side (-X)", 17, BLUE, "middle", "bold",
                f"transform='rotate(90 {x1 + 38:.1f} {CY:.1f})'"))
    # FLOWERs
    for fl in F.flower_positions():
        fx, fy = fl["xy"]
        o.append(f"<circle cx='{sx(fx):.1f}' cy='{sy(fy):.1f}' r='{fl['radius'] * S:.1f}' "
                 f"fill='#f2a8cc' stroke='#b03070' stroke-width='2.5'/>")
    fa = next(fl for fl in F.flower_positions() if fl["xy"][1] > 60)
    o.append(_t(sx(fa["xy"][0]) - 26, sy(fa["xy"][1]) + 4, "FLOWER", 12, "#b03070", "end",
                "bold"))
    # HIVE frame footprint (foot bars at x = +-24.73, y = +-19.47), beams, audience CELLs
    fxh, fyh = 24.73, 19.47
    o.append(f"<rect x='{sx(fxh):.1f}' y='{sy(-fyh):.1f}' width='{2 * fxh * S:.1f}' "
             f"height='{2 * fyh * S:.1f}' fill='#ffffff' fill-opacity='0.6' stroke='#444' "
             f"stroke-width='4'/>")
    for x, col in ((12.75, RED), (-12.75, BLUE)):
        o.append(_line(sx(x), sy(-fyh), sx(x), sy(fyh), col, 9, "stroke-linecap='round'"))
        o.append(f"<circle cx='{sx(x):.1f}' cy='{sy(15.77):.1f}' r='12' fill='#ffffff' "
                 f"stroke='{col}' stroke-width='4'/>")
    o.append(_t(CX, sy(-fyh) - 12, "HIVE (both audience CELLs tipped UP for calibration)", 14,
                INK, "middle", "bold"))
    # kit tags: 100/101 on the audience logo panel, 102/103 at the audience base corners
    for tid, tx, ty, dx, dy, anchor in ((101, 10.0, 2.9, -24, 5, "end"),
                                        (100, -10.0, 2.9, 24, 5, "start"),
                                        (103, 21.73, 19.06, 0, 24, "middle"),
                                        (102, -21.73, 19.06, 0, 24, "middle")):
        o.append(f"<rect x='{sx(tx) - 15:.1f}' y='{sy(ty) - 6:.1f}' width='30' height='12' "
                 f"fill='#222'/>")
        o.append(_t(sx(tx) + dx, sy(ty) + dy, f"tag {tid}", 13, INK, anchor, "bold"))
    # cameras: sight line, floor cross, tripod feet, plumb spot
    r = TRIPOD_LEG_RADIUS_IN
    for k in ("A", "B"):
        c, col = n[k], COL[k]
        px, py = sx(c["pos"][0]), sy(c["pos"][1])
        ax, ay = sx(c["aim"][0]), sy(c["aim"][1])
        o.append(_line(px, py, ax, ay, col, 3, "stroke-dasharray='10 7'"))
        o.append(_line(ax - 9, ay - 9, ax + 9, ay + 9, col, 4))
        o.append(_line(ax - 9, ay + 9, ax + 9, ay - 9, col, 4))
        for dx, dy in ((0.0, r), (r * 0.866, -r / 2), (-r * 0.866, -r / 2)):
            o.append(_line(px, py, px + dx * S, py + dy * S, "#888", 3))
            o.append(f"<circle cx='{px + dx * S:.1f}' cy='{py + dy * S:.1f}' r='6' "
                     f"fill='#888'/>")
    a, b = n["A"], n["B"]
    ax_, ay_ = sx(a["aim"][0]), sy(a["aim"][1])
    bx_, by_ = sx(b["aim"][0]), sy(b["aim"][1])
    o.append(_t(ax_ + 16, ay_ - 8, "floor cross A", 13, COL["A"], "start", "bold"))
    o.append(_t(bx_ - 18, by_ - 2, "floor cross B", 13, COL["B"], "end", "bold"))
    # tape dimensions
    outer_y = y1 + wt  # outside face of the audience wall
    pax, pay = sx(a["pos"][0]), sy(a["pos"][1])
    pbx, pby = sx(b["pos"][0]), sy(b["pos"][1])
    o.append(_line(pbx + 120, pby, pax - 120, pay, "#555", 1.6, "stroke-dasharray='4 6'"))
    o.append(_dim_v(CX - 150, outer_y, pay, f"{a['out_in']:.0f} in out from the outside of "
                    "the wall", "#333", 1))
    dy_a = pay + r * S + 34
    o.append(_line(pax, pay + r * S + 8, pax, dy_a + 8, COL["A"], 1.2))
    o.append(_line(x1 + wt, outer_y, x1 + wt, dy_a + 8, COL["A"], 1.2,
                   "stroke-dasharray='3 5'"))
    o.append(_dim_h(pax, x1 + wt, dy_a, f"{a['along_in']:.1f} in", COL["A"]))
    # camera labels
    lx = x1 + 60
    for i, s in enumerate((
            "CAMERA A  =  cam0",
            f"lens {a['lens_height_in']:.0f} in above the floor",
            f"{a['out_in']:.0f} in out from the wall,",
            f"{a['along_in']:.1f} in from the BLUE-side",
            "wall's outer edge",
            "aim: level, at floor cross A")):
        o.append(_t(lx, pay - 30 + i * 21, s, 17 if i == 0 else 15, COL["A"], "start",
                    "bold" if i == 0 else "normal"))
    for i, s in enumerate((
            "CAMERA B  =  cam1",
            f"lens {b['lens_height_in']:.0f} in above the floor",
            f"{b['out_in']:.0f} in out from the wall,",
            f"{b['along_in']:.1f} in from the RED-side",
            "wall's outer edge (at the corner)",
            "aim: tilted up 12 deg, floor cross B")):
        o.append(_t(24, pby + 62 + i * 21, s, 17 if i == 0 else 15, COL["B"], "start",
                    "bold" if i == 0 else "normal"))
    # PC table and cable runs along the floor
    tx0, tx1, ty0, ty1 = CX - 165, CX + 165, sy(h) + 215, sy(h) + 275
    o.append(f"<rect x='{tx0:.1f}' y='{ty0:.1f}' width='{tx1 - tx0:.1f}' "
             f"height='{ty1 - ty0:.1f}' rx='8' fill='#fff6d8' stroke='#8a6d00' "
             f"stroke-width='3'/>")
    o.append(_t(CX, ty0 + 26, "PC TABLE", 17, "#5c4800", "middle", "bold"))
    o.append(_t(CX, ty0 + 47, "behind the cameras, within cable reach", 13, "#5c4800",
                "middle"))
    cym = (ty0 + ty1) / 2
    o.append(f"<polyline points='{pax:.1f},{pay:.1f} {pax - 40:.1f},{pay + 55:.1f} "
             f"{pax - 40:.1f},{cym + 12:.1f} {tx1:.1f},{cym + 12:.1f}' fill='none' "
             f"stroke='{COL['A']}' stroke-width='4'/>")
    o.append(f"<polyline points='{pbx:.1f},{pby:.1f} {pbx + 40:.1f},{pby + 55:.1f} "
             f"{pbx + 40:.1f},{cym + 12:.1f} {tx0:.1f},{cym + 12:.1f}' fill='none' "
             f"stroke='{COL['B']}' stroke-width='4'/>")
    o.append(_t(tx1 + 12, cym + 34, "cable A to PC port 1", 14, COL["A"], "start", "bold"))
    o.append(_t(tx0 - 12, cym + 34, "cable B to PC port 2", 14, COL["B"], "end", "bold"))
    for k in ("A", "B"):  # camera dots last, so cables and sight lines never cover the letters
        px, py = sx(n[k]["pos"][0]), sy(n[k]["pos"][1])
        o.append(f"<circle cx='{px:.1f}' cy='{py:.1f}' r='19' fill='{COL[k]}' stroke='#fff' "
                 f"stroke-width='3'/>")
        o.append(_t(px, py + 7, k, 20, "#ffffff", "middle", "bold"))
    o.append(_t(CX, ty1 + 34, "AUDIENCE SIDE: you stand here", 18, INK, "middle", "bold"))
    # legend
    ly = ty1 + 66
    for i, s in enumerate((
            f"Floor cross A: from field centre, {abs(a['aim'][0]):.0f} in toward RED and "
            f"{a['aim'][1]:.0f} in toward the audience.   Floor cross B: {abs(b['aim'][0]):.0f}"
            f" in toward RED and {b['aim'][1]:.0f} in toward the audience.",
            "Grey dots: tripod feet. One leg points straight away from the wall; no foot "
            "touches the wall. Dashed lines: where each camera looks. Keep people out of them.",
            "Black bars: the four printed tags. 100 and 101 lie on the slanted logo panel; "
            "102 and 103 stand at the HIVE's base corners on the audience side.")):
        o.append(_t(30, ly + i * 22, s, 14, "#333"))
    o.append("</svg>")
    return "\n".join(o)


# ------------------------------------------------------------------ wiring
WW, WH = 1240, 610


def _box(x, y, w, h, fill, stroke, lines, col=INK):
    out = [f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='10' fill='{fill}' "
           f"stroke='{stroke}' stroke-width='3'/>"]
    for i, (s, size, weight) in enumerate(lines):
        out.append(_t(x + w / 2, y + 30 + i * 22, s, size, col, "middle", weight))
    return "".join(out)


def wiring_svg() -> str:
    o: list[str] = [
        f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {WW} {WH}' width='{WW}' "
        f"height='{WH}'>",
        f"<rect width='{WW}' height='{WH}' fill='#ffffff'/>",
        _t(30, 42, "How to wire it: one cable run per camera, straight into the PC", 26, INK,
           "start", "bold"),
        _t(30, 68, "USB carries both the picture and the power. The cameras have no power "
           "brick and no batteries.", 15),
        # PC
        "<rect x='960' y='105' width='250' height='330' rx='12' fill='#fff6d8' "
        "stroke='#8a6d00' stroke-width='3'/>",
        _t(1085, 262, "PC", 30, "#5c4800", "middle", "bold"),
        _t(1085, 288, "running HiveShotTracker", 14, "#5c4800", "middle"),
        _t(1085, 310, "laptop on its charger", 14, "#5c4800", "middle"),
    ]
    for k, y, cam_id, port in (("A", 160, "cam0", 1), ("B", 370, "cam1", 2)):
        col = COL[k]
        o.append(_box(30, y - 55, 230, 110, "#ffffff", col, (
            (f"CAMERA {k}  =  {cam_id}", 18, "bold"),
            ("Arducam on its bracket", 14, "normal"),
            ("and tripod", 14, "normal")), col))
        # camera's own cable
        o.append(_line(260, y, 430, y, col, 5))
        o.append(_t(345, y - 14, CAMERA_CABLE.split(" (")[0], 13, col, "middle", "bold"))
        o.append(_t(345, y + 24, "(about 3 ft)", 13, col, "middle"))
        # join: plug into the extension's socket
        o.append(f"<rect x='430' y='{y - 14}' width='34' height='28' rx='4' fill='{col}'/>")
        o.append(f"<rect x='468' y='{y - 18}' width='44' height='36' rx='4' fill='#ffffff' "
                 f"stroke='{col}' stroke-width='4'/>")
        o.append(_t(471, y + 50, "socket end of the", 13, GREY, "middle"))
        o.append(_t(471, y + 67, "extension: camera side", 13, GREY, "middle"))
        # extension
        o.append(_line(512, y, 900, y, col, 9, "stroke-linecap='round'"))
        o.append(_t(706, y - 18, EXTENSION, 15, col, "middle", "bold"))
        o.append(_t(706, y + 28, "along the floor outside the wall, taped down", 13, GREY,
                    "middle"))
        # plug into the PC port
        o.append(f"<rect x='900' y='{y - 14}' width='44' height='28' rx='4' fill='{col}'/>")
        o.append(f"<rect x='960' y='{y - 22}' width='30' height='44' fill='#2a6fdb' "
                 f"stroke='#12408a' stroke-width='2'/>")
        o.append(_t(1000, y - 2, f"USB port {port}", 16, "#5c4800", "start", "bold"))
        o.append(_t(1000, y + 18, "blue = USB 3.0", 13, "#5c4800", "start"))
        o.append(_t(944, y + 50, "plug end: PC side", 13, GREY, "end"))
    notes = (
        ("1.", "Each camera gets its OWN port on the PC. Never plug both cameras into one hub, "
               "dock or splitter: the frame rate collapses."),
        ("2.", "The extension works in one direction only: plug end into the PC, socket end "
               "toward the camera."),
        ("3.", "Not enough USB-A ports on the laptop? Use one USB-C adapter per camera, each "
               "in a different USB-C port."),
        ("4.", "Label both ends of each cable A or B with tape. In the app, camera A must "
               "show up as cam0 and camera B as cam1."),
    )
    for i, (num, s) in enumerate(notes):
        o.append(_t(34, 482 + i * 28, num, 16, INK, "start", "bold"))
        o.append(_t(62, 482 + i * 28, s, 16, INK))
    o.append("</svg>")
    return "\n".join(o)


# ------------------------------------------------------------------ output
BROWSERS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
)


def render_png(svg_path: Path, png_path: Path, width: int, height: int) -> bool:
    """Rasterise an SVG with a headless Chromium browser. False when none is installed."""
    exe = next((b for b in BROWSERS if Path(b).exists()), None)
    if exe is None:
        return False
    subprocess.run([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    f"--window-size={width},{height}", f"--screenshot={png_path}",
                    svg_path.resolve().as_uri()], check=True, capture_output=True, timeout=120)
    return png_path.exists()


def main(argv: list[str]) -> None:
    n = builder_numbers()
    jobs = (("builder_field_map", field_map_svg(n), W, H),
            ("builder_wiring", wiring_svg(), WW, WH))
    for stem, svg, w, h in jobs:
        path = DOCS / f"{stem}.svg"
        path.write_text(svg, encoding="utf-8", newline="\n")
        print(f"wrote {path}")
        if "--png" in argv:
            png = DOCS / f"{stem}.png"
            print(f"wrote {png}" if render_png(path, png, w, h)
                  else "no Edge or Chrome found: PNG skipped")
    for k in ("A", "B"):
        c = n[k]
        print(f"camera {k}: lens {c['lens_height_in']:.0f} in, {c['out_in']:.1f} in out, "
              f"{c['along_in']:.1f} in along, aim floor ({c['aim'][0]:+.0f}, {c['aim'][1]:+.0f}),"
              f" yaw {c['yaw_deg']:.0f}, pitch {c['pitch_deg']:+.0f}")


if __name__ == "__main__":
    main(sys.argv[1:])

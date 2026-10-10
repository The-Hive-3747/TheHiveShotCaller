"""Parametric 3D-printable tripod bracket for a bare Arducam USB camera board.

Run:  .venv\\Scripts\\python.exe tools\\make_bracket.py
Writes docs/camera_bracket.stl and docs/camera_bracket.png (millimetres).

Coordinate frame (print orientation): X = width, Y = depth (camera looks toward -Y),
Z = up.  The base plate sits on the bed (z = 0); the vertical plate stands at
y in [-PLATE_T, 0] and the board mounts to its front (-Y) face.

If your board's mounting-hole pitch is outside 26-32 mm, change HOLE_PITCH_MM (the
slot centre pitch) and/or PITCH_MIN / PITCH_MAX (which size the slots) and regenerate.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import trimesh
from trimesh import transformations as tf

# ---------------------------------------------------------------- parameters (mm)
PLATE_W = 44.0  # vertical plate width (X)
TOTAL_H = 50.0  # overall height, bed to top of vertical plate (Z)
PLATE_T = 4.0  # vertical plate thickness (Y)
BASE_W = 44.0  # base plate width (X)
BASE_D = 40.0  # base plate depth behind the vertical plate (Y, y in [0, BASE_D])
BASE_T = 7.0  # base plate thickness (Z); 7 leaves a 1.2 mm ledge under the nut pocket
GUSSET_T = 4.0  # gusset thickness (X); 4 keeps nuts at 30 mm pitch clear (x < 18)
GUSSET_LEG = 22.0  # gusset leg length along Y and Z

LENS_HOLE_D = 20.0
BOARD_SIZE = 34.0
# Slot centre pitch.  Slots are sized to span PITCH_MIN..PITCH_MAX around this value.
HOLE_PITCH_MM = 29.0
PITCH_MIN, PITCH_MAX = 26.0, 32.0
SLOT_W = 2.4
BOSS_D = 5.0
BOSS_H = 3.0
USB_NOTCH_W = 12.0
USB_NOTCH_H = 6.0  # depth measured inward from the board's top edge

NUT_AF = 11.2  # 1/4-20 nut across flats
NUT_DEPTH = 5.8
NUT_THRU_D = 7.0
ZIP_D = 4.0
ZIP_X = 14.0
ZIP_Y = 32.0

# Board centre height: 3.5 mm margin above the 34 mm board's top edge
BOARD_CZ = TOTAL_H - 3.5 - BOARD_SIZE / 2.0

ROOT = Path(__file__).resolve().parents[1]
STL_PATH = ROOT / "docs" / "camera_bracket.stl"
PNG_PATH = ROOT / "docs" / "camera_bracket.png"

_ROT_X90 = tf.rotation_matrix(math.pi / 2.0, [1, 0, 0])  # cylinder axis Z -> Y


def slot_length() -> float:
    """Overall slot length so every pitch PITCH_MIN..PITCH_MAX (square pattern) fits."""
    travel = (PITCH_MAX - PITCH_MIN) * math.sqrt(2.0) / 2.0  # hole-centre travel on diagonal
    return travel + SLOT_W


def _box(extents, center) -> trimesh.Trimesh:
    return trimesh.creation.box(extents=extents, transform=tf.translation_matrix(center))


def _union(parts):
    return trimesh.boolean.union(parts, engine="manifold")


def _stadium(length, width, y0, y1, cx, cz, theta) -> trimesh.Trimesh:
    """Stadium prism spanning y0..y1 centred at (cx, cz), long axis rotated theta about Y."""
    h = y1 - y0
    cy = (y0 + y1) / 2.0
    straight = max(length - width, 1e-3)
    place = tf.translation_matrix([cx, cy, cz]) @ tf.rotation_matrix(theta, [0, 1, 0])
    parts = [trimesh.creation.box(extents=[straight, h, width], transform=place)]
    for s in (-1, 1):
        parts.append(
            trimesh.creation.cylinder(
                radius=width / 2.0,
                height=h,
                sections=48,
                transform=place @ tf.translation_matrix([s * straight / 2.0, 0, 0]) @ _ROT_X90,
            )
        )
    return _union(parts)


def _gusset(x_center: float) -> trimesh.Trimesh:
    """Right-triangle gusset in the YZ plane, GUSSET_T thick along X."""
    e = 0.5  # sink into plate/base so the union overlaps
    pts = [
        (-e, BASE_T - e),
        (GUSSET_LEG, BASE_T - e),
        (GUSSET_LEG, BASE_T),
        (-e, BASE_T + GUSSET_LEG),
    ]
    v = [(x, y, z) for x in (x_center - GUSSET_T / 2, x_center + GUSSET_T / 2) for y, z in pts]
    return trimesh.convex.convex_hull(np.array(v))  # shape is convex


def build() -> trimesh.Trimesh:
    half_w = PLATE_W / 2.0
    # ---- solid body
    vplate = _box([PLATE_W, PLATE_T, TOTAL_H], [0, -PLATE_T / 2.0, TOTAL_H / 2.0])
    base = _box([BASE_W, BASE_D, BASE_T], [0, BASE_D / 2.0, BASE_T / 2.0])
    gx = half_w - GUSSET_T / 2.0
    gussets = [_gusset(-gx), _gusset(gx)]

    slen = slot_length()
    r_nom = HOLE_PITCH_MM * math.sqrt(2.0) / 2.0
    bosses, slots = [], []
    for sx in (-1, 1):
        for sz in (-1, 1):
            dx, dz = sx / math.sqrt(2.0), sz / math.sqrt(2.0)
            theta = -math.atan2(dz, dx)
            cx, cz = r_nom * dx, BOARD_CZ + r_nom * dz
            boss_len = slen - SLOT_W + BOSS_D  # boss end radius concentric with slot end radius
            bosses.append(
                _stadium(boss_len, BOSS_D, -PLATE_T - BOSS_H, -PLATE_T + 0.5, cx, cz, theta)
            )
            slots.append(_stadium(slen, SLOT_W, -PLATE_T - BOSS_H - 1, 1.0, cx, cz, theta))

    body = _union([vplate, base, *gussets, *bosses])

    # ---- cuts
    cuts = list(slots)
    front_depth = PLATE_T + BOSS_H + 4.0
    cuts.append(
        trimesh.creation.cylinder(
            radius=LENS_HOLE_D / 2.0,
            height=front_depth,
            sections=96,
            transform=tf.translation_matrix([0, -PLATE_T / 2.0 - BOSS_H / 2.0, BOARD_CZ])
            @ _ROT_X90,
        )
    )
    # USB connector notch: open to the top edge, USB_NOTCH_H deep below the board's top edge
    z0 = BOARD_CZ + BOARD_SIZE / 2.0 - USB_NOTCH_H
    cuts.append(
        _box(
            [USB_NOTCH_W, front_depth, TOTAL_H - z0 + 1.0],
            [0, -PLATE_T / 2.0 - BOSS_H / 2.0, (z0 + TOTAL_H + 1.0) / 2.0],
        )
    )
    # 1/4-20 nut pocket from the underside (open to the bed) + through hole
    nut_cy = BASE_D / 2.0
    cuts.append(
        trimesh.creation.cylinder(
            radius=NUT_AF / math.sqrt(3.0),  # circumradius of a regular hexagon
            height=NUT_DEPTH + 1.0,
            sections=6,
            transform=tf.translation_matrix([0, nut_cy, (NUT_DEPTH - 1.0) / 2.0]),
        )
    )
    cuts.append(
        trimesh.creation.cylinder(
            radius=NUT_THRU_D / 2.0,
            height=BASE_T + 2.0,
            sections=64,
            transform=tf.translation_matrix([0, nut_cy, BASE_T / 2.0]),
        )
    )
    for sx in (-1, 1):
        cuts.append(
            trimesh.creation.cylinder(
                radius=ZIP_D / 2.0,
                height=BASE_T + 2.0,
                sections=32,
                transform=tf.translation_matrix([sx * ZIP_X, ZIP_Y, BASE_T / 2.0]),
            )
        )

    mesh = trimesh.boolean.difference([body, _union(cuts)], engine="manifold")
    mesh.merge_vertices()
    mesh.remove_unreferenced_vertices()
    trimesh.repair.fix_normals(mesh)
    return mesh


def render_png(mesh: trimesh.Trimesh, path: Path, px_per_mm: float = 7.0) -> None:
    """Front / side / top orthographic views plus an isometric view, drawn with cv2."""
    import cv2

    light = np.array([0.35, -0.6, 0.72])
    light /= np.linalg.norm(light)
    verts, faces, normals = mesh.vertices, mesh.faces, mesh.face_normals

    def panel(rot: np.ndarray, title: str) -> np.ndarray:
        # rot maps world -> view; view x right, view y up, view z toward viewer
        v = verts @ rot.T
        n = normals @ rot.T
        lo, hi = v.min(0), v.max(0)
        w, h = (int(c) for c in np.ceil((hi - lo)[:2] * px_per_mm) + 40)
        img = np.full((h + 30, max(w, 330), 3), 245, np.uint8)
        order = np.argsort(v[faces][:, :, 2].mean(1))  # far to near
        for fi in order:
            if n[fi, 2] <= 1e-6:
                continue
            tri = v[faces[fi]]
            px = (tri[:, 0] - lo[0]) * px_per_mm + 20
            py = h - ((tri[:, 1] - lo[1]) * px_per_mm + 20)
            pts = np.stack([px, py], 1).round().astype(np.int32)
            shade = 0.35 + 0.65 * max(0.0, float(n[fi] @ (rot @ light)))
            col = tuple(int(c * shade) for c in (205, 160, 70))  # BGR
            cv2.fillPoly(img, [pts], col, cv2.LINE_AA)
        cv2.putText(
            img, title, (8, h + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (30, 30, 30), 1, cv2.LINE_AA
        )
        return img

    # front (camera side, looking +Y): view x = world x, view y = world z, view z = -world y
    front = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], float)
    # side (viewer at +X looking -X): view x = world y, so the camera side (-y) is at the left
    side = np.array([[0, 1, 0], [0, 0, 1], [1, 0, 0]], float)
    # top (viewer above): view x = world x, view y = world y, so the camera side is at the bottom
    top = np.eye(3)
    # isometric from front-right-above
    yaw = tf.rotation_matrix(math.radians(-35.0), [0, 0, 1])[:3, :3]
    pitch = tf.rotation_matrix(math.radians(25.0), [1, 0, 0])[:3, :3]
    iso = pitch @ front @ yaw
    panels = [
        panel(front, "Front (camera side)"),
        panel(side, "Side (camera at left)"),
        panel(top, "Top (camera at bottom)"),
        panel(iso, "Isometric"),
    ]
    hmax = max(p.shape[0] for p in panels)
    padded = [
        np.vstack([p, np.full((hmax - p.shape[0], p.shape[1], 3), 245, np.uint8)]) for p in panels
    ]
    cv2.imwrite(str(path), np.hstack(padded))


def main() -> None:
    mesh = build()
    STL_PATH.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(STL_PATH, file_type="stl")  # binary STL
    render_png(mesh, PNG_PATH)
    print(
        f"watertight={mesh.is_watertight} volume_cm3={mesh.volume / 1000:.2f} "
        f"extents={np.round(mesh.extents, 2).tolist()} faces={len(mesh.faces)}"
    )


if __name__ == "__main__":
    main()

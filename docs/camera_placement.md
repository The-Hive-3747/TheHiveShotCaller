# Camera placement (draft, from `hiveshot/placement.py`)

Map: `docs/camera_placement.png` (same content as `camera_placement.svg`). Top-down, X right, Y up, **audience side (the red up CELL) at the top**. Origin = field center. Wall = +-72 in, which is the **INSIDE face** of the wall (see section 2). Tiles 24 in. Regenerate: `.venv\Scripts\python.exe -c "from hiveshot import placement as p; p.write_map('gopro','docs/camera_placement.svg','docs/camera_placement.png')"`.

## 0. Which camera is which

| Label | App source id | Where it stands | Looks toward |
|---|---|---|---|
| **A** | **`cam0`** | outside the -X wall, near the audience (+Y) corner | across the field toward +X, slightly away from the audience |
| **B** | **`cam1`** | outside the +Y (audience) wall, near the +X corner | across the field toward -X, away from the audience |
| C (optional, exit speed) | `cam2` (not needed for the two-camera pipeline) | outside the +Y wall | down at the launch zone |

Field axes (same as the app and the 3-D viewer): origin at field center, Z up, **+Y toward the audience**, X along the red/blue axis, **red HIVE at X = -12.75 (the -X half), blue at +12.75**. Standing at the audience wall facing the field, -X (red) is on your **right**. The map is drawn with the audience at the top, so it looks mirrored compared with what you see standing at the audience wall; use the labels and the table below, not "left" and "right". Check once at the field that the red HIVE is the one on your right when you stand at the audience wall (VERIFY: if the real layout is the other way round, mirror every X in this document and tell the developer).

Option A (GoPro over RTMP): publish camera A to `rtmp://<PC-IP>:1935/cam0` and camera B to `.../cam1`. Capture card or USB camera: the device index order is not guaranteed. Wave a hand in front of A and watch which Calibration-tab card (`cam0` or `cam1`) shows it; swap the two source rows in Settings if it is wrong. Never assume the index order.

## 1. Equipment

| | Option A: GoPro (2 + optional 3rd) | Option B: USB global shutter |
|---|---|---|
| Cameras | 2x GoPro HERO12/13 + Media Mod | 2x Arducam 2.3 MP global shutter (USB 2.0) |
| Link | micro-HDMI 10 ft to Cam Link 4K | 16 ft active USB extension, **straight into its own USB port on the PC** (no hub) |
| Power | USB-C wall power (battery ~1 h) | USB bus power from the PC port |
| Mount | 60 in tripod + 1/4-20 adapter | 60 in tripod + board case |
| Exit-speed camera C | optional 3rd camera (USB Arducam on 16 ft ext.) | same, optional 3rd Arducam |
| Also | painter's tape, tape measure, phone level app, plumb line, string, checkerboard (see calibration.md) | same |

## 2. Camera positions (inches; tripods are 6 in beyond the INSIDE face of the wall)

Positions are the same for A and B in both options; only the FOV differs.

**What the numbers mean.** The coordinates and the "+-72 in" wall are the **inside face** of the perimeter wall (the face the robot sees). A person outside the field can only reach the outside face. The FTC perimeter wall is assumed to be **1.5 in thick (VERIFY with a tape on your wall and use the real number)**. So:

- Distance from the **outside face** to the lens = 6 in (clearance from the inside face) minus the wall thickness = **4.5 in** for a 1.5 in wall (in general 6 - t).
- The lens position is the spot **under the lens** (drop a plumb line from the lens). The tripod feet are not the reference; draw the foot triangle around the plumb spot.
- Distance along a wall is measured **parallel to the wall from the outer edge of the adjacent perpendicular wall** (the corner): inside-face distance 7 in + wall thickness 1.5 in = **8.5 in** for A and B.

| Cam | App id | Role | From field center (x, y) | Lens height | Tape: out from the OUTSIDE face / along the wall from the corner's outer edge | Aim: yaw (bearing from +X toward +Y) | Pitch | Aim point (x, y, z) |
|---|---|---|---|---|---|---|---|---|
| A | `cam0` | primary | (-78, +65) | 36 in | 4.5 in out from the -X wall; 8.5 in along it from the +Y wall's outer edge (corner (-72,+72) on the inside face) | **340 deg** (across the field toward +X, 20 deg toward -Y, i.e. slightly away from the audience) | **+20 deg** up | (-13, +41, 61) |
| B | `cam1` | primary | (+65, +78) | 36 in | 4.5 in out from the +Y wall; 8.5 in along it from the +X wall's outer edge (corner (+72,+72) on the inside face) | **205 deg** (across the field toward -X, 25 deg toward -Y, i.e. away from the audience) | **+16 deg** up | (-13, +41, 61) |
| C | `cam2` | exit speed (optional) | Option A: (-25, +78); Option B: (-13, +78) | 58 in | 4.5 in out from the +Y wall; 48.5 in (Option A) / 60.5 in (Option B) along it from the -X wall's outer edge | 294 deg (A) / 270 deg (B) | -42 deg (A) / -45 deg (B), down | (-13, +50, 30), the launch zone |

Yaw is a bearing in **field coordinates**: 0 deg = toward +X, 90 deg = toward +Y (the audience), 180 deg = toward -X, 270 deg = toward -Y. A phone compass is useless indoors; use the aiming method below.

**Aiming method (no software, about 2 minutes per camera).**

1. **Floor mark.** Put a tape cross on the field floor at **(-13, +41)**: 13 in to the -X (red) side of the center line and 41 in toward the audience from field center. It is the point on the floor straight below the aim point; the audience-side CELL is at y = +24, so the mark is 17 in in front of it, toward the audience.
2. **Yaw.** Stretch a string from the plumb spot under the lens to the cross, or sight over the lens, and turn the tripod head until the lens points along the string. Tolerance about 3 deg.
3. **Pitch and roll.** Lay a phone with a level app on top of the camera body (or use the tripod's own level). Set the pitch from the table (A +20, B +16), +-2 deg. Roll must read 0 deg, +-1 deg.
4. **Check in the app preview** (Calibration tab, **Refresh image**). This is the real acceptance test:
   - The **up-CELL opening** (the tilted 20 in wide opening of the red HIVE nearest the audience) is near the middle: its center at about **61 % from the left and 54 % from the top** in A (59 / 54 for the Arducam), and about **42 % from the left and 53 % from the top** in B (43 / 53).
   - **All 8 calibration points are visible, at least 20 px inside the image edge**: the four corners of that opening and the four top corners of the HIVE frame (calibration.md shows where each appears). In B the far-side +X frame corner (point 8) is the nearest to the left edge: if it is cut off, turn B a few degrees **counter-clockwise seen from above** (turn left; yaw 205 becomes 208, i.e. aim a little more toward the far side, away from the audience) until it is visible. B can only be off by about 1.5 deg clockwise (about 7 deg for the Arducam) but about 29 deg counter-clockwise; A can be off by about 6 deg counter-clockwise (about 11 deg for the Arducam) and 29 deg clockwise.
   - The **launch area is below the bottom edge of the picture, on purpose**: the cameras look up at the HIVE, and the ball flies up into view from the bottom edge. Do not tilt down to get the launch zone in frame: that pushes the HIVE corners out of the top.

   The extrinsic calibration measures each camera's true pose from the 8 points, so the tolerances above are about keeping the 8 points and the ball paths in frame, not about hitting the table values to the degree.
5. **In-frame roll check.** The frame's audience-side top bar (calibration points 5 and 6) is **not** level in the picture at these camera positions: it runs along the line of sight, so perspective tilts it. With the camera leveled it looks like this: in A it runs from the upper right down to the lower left, about **30 deg below horizontal** (for every 100 px it moves left it drops about 57 px); in B it runs from the lower right up to the upper left, about **23 deg above horizontal** (100 px left, 42 px up). If the bar's slope differs from this by more than about 3 deg, the camera is rolled or aimed wrong: re-check the level and the yaw.

Aim point: the middle of the image is on the point 17 in in front of the HIVE up CELL's audience opening, 61 in high.

Lens: Option A GoPro Linear lens, **86 deg HFOV**. Option B Arducam **110 deg diagonal, treated as 95 deg HFOV** (assumption, lens dependent; the intrinsics calibration measures the real one, see calibration.md section 2).

## 3. Settings

| Setting | Option A (GoPro) | Option B (Arducam) |
|---|---|---|
| Resolution / rate | 1080p, 60 fps via HDMI (30 fps while recording to SD) | 1920x1080, 90 fps, MJPG |
| Lens | Linear | n/a, set focus at the HIVE (~100 in), lock it |
| Stabilization | HyperSmooth OFF | n/a |
| Exposure | shutter fixed, no auto-lowlight | fixed exposure, short (about 1/500) |
| Cable | micro-HDMI to Cam Link; separate USB-C power | USB extension to **its own PC port** (see step 6) |

## 4. Step by step

1. Clear the field. Set the HIVE in its normal state with the red up CELL toward +Y (audience side).
2. From each corner named in the table, measure along the wall (from the outer corner edge), then out from the **outside face** of the wall (4.5 in for a 1.5 in wall; section 2). Mark the spot under the lens with a painter's tape cross and the three tripod feet as a triangle around it. Label it A, B, C and write the app id (`cam0`, `cam1`) next to it.
3. Extend each tripod to the lens height in the table. Lens centered over the tape cross (plumb line).
4. Put the floor cross at (-13, +41) and aim each camera with the aiming method in section 2: yaw by string, pitch and roll with the level app.
5. Check the preview against section 2 step 4 and step 5. All 8 calibration points must be visible.
6. Cable: run all cables along the floor outside the wall, tape them down, and keep them out of the tripod legs. **Option B (two USB 2.0 Arducam cameras): each camera, through its own extension, goes directly into its own USB port on the PC.** Two cameras must not share one hub link (no hub, powered or not, between a camera and the PC): two 1080p90 MJPEG streams starve a single USB 2.0 hub link and fps drops. If front-panel ports share one internal hub, use one front and one rear port, then confirm fps in the app. Option A: each Cam Link into its own USB 3 port.
7. Open the app preview (Calibration tab). Confirm in `cam0` (A) and `cam1` (B) that the CELL opening and all 8 reference points are in frame and that the ball path will enter from the bottom edge.
8. Run the calibration (docs/calibration.md). Write the date next to the tape marks.

## 5. Pre-session checklist

- [ ] Tripod feet on tape, legs locked, camera tight on its mount.
- [ ] Lens height, yaw and pitch match the table; level app reads roll 0; HyperSmooth OFF; Linear lens (Option A).
- [ ] `cam0` is A and `cam1` is B (hand in front of A shows on the `cam0` card).
- [ ] Option B: the two cameras are in two different PC ports, no hub.
- [ ] Focus locked at the HIVE (Option B). Lens clean.
- [ ] Batteries topped up or USB-C power connected (Option A).
- [ ] All cameras show live video at the expected fps (60 / 90) with no dropped frames.
- [ ] Lighting: no window or bright light **behind** the HIVE (it silhouettes the ball). Light from above or from the audience side is best. Keep the orange/yellow ball in even light.
- [ ] Calibration error under 2 px at every one of the 8 points (calibration.md); a test ball ends its track at the CELL opening.
- [ ] Ball test: throw 3 balls; each is tracked in both cameras for the whole flight.

## 6. Expected numbers (pollen ball, 2.8 in, 1080p; from the simulated sample shots)

| | Option A (86 deg) | Option B (95 deg) |
|---|---|---|
| Ball diameter, cam A | 31 to 84 px (mean 39) | 27 to 76 px (mean 34) |
| Ball diameter, cam B | 27 to 61 px (mean 33) | 23 to 55 px (mean 28) |
| Ball diameter, cam C (first 0.2 s) | 46 to 139 px | 47 to 122 px |
| Mean triangulation angle A/B | 117 deg (target 60 to 120) | 118 deg |
| Sample points seen by both A and B | 91 % | 93 % |
| Points where the HIVE frame blocks a ray | 0 % | 0 % |

If the ball is under 10 px or the triangulation angle is outside 60 to 120 deg, the cameras are off their marks.

## 7. Assumptions

Shots are lobs of 230 in/s from 12 in height, 50 to 66 in from field center along +Y, x within 30 in of the red HIVE; the ball is cut where it crosses the opening. Pinhole camera, no distortion. A tripod head can stand 6 in beyond the inside face of the wall (4.5 in from the outside face for a 1.5 in wall, VERIFY). Corner tripods may be limited by the audience barrier: slide a camera along the wall and re-run `recommend()` if needed. The HIVE frame size and top height used for calibration points 5 to 8 are CAD guesses (VERIFY). This is a draft for M1 test footage; finalize after the first footage.

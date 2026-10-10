# Camera placement (draft, from `hiveshot/placement.py`)

Map: `docs/camera_placement.png` (same content as `camera_placement.svg`). Top-down, X right, Y up, **audience side (the red up CELL) at the top**. Origin = field center. Wall = +-72 in, which is the **INSIDE face** of the wall (see section 2). Tiles 24 in. Regenerate: `.venv\Scripts\python.exe -c "from hiveshot import placement as p; p.write_map('gopro','docs/camera_placement.svg','docs/camera_placement.png')"`.

All field geometry (CELL opening, tag rows, frame, beams) is read from `hiveshot/field.py`, which follows the official CAD: the red up-CELL opening center is at (+12.75, 15.77, 59.55) and its AprilTag row at (+12.75, 13.10, 49.79). **Red is the +X HIVE, blue the -X HIVE.**

**What changed (tag-aware placement).** The field's own AprilTags sit on the underside of each CELL, facing down toward the tiles and toward the audience side. Both cameras must read them, and they must read the printed calibration tags too. The first draft (lens 36 in high, on the side walls) looked at the up-CELL sticker 63 to 64 deg off its normal, too oblique to read. The search now requires, for each camera: the sticker under 55 deg off its normal, all four sticker tags and at least three of the four printed kit tags inside the picture (60 px margin) with a usable size (sticker tag edge at least 14 px, kit tag edge at least 28 px), and all 8 calibration points in frame (60 px margin); and for the pair: 90 % of the sample ball arcs in both cameras with a 60 to 120 deg triangulation angle. Lens heights 12 to 58 in and positions every 12 in along the audience wall were added to the search, and one set of tripod spots has to work for both lens options. Result: **both cameras stand on the audience (+Y) wall, one at x = -36 with the lens 30 in high, one at x = +36 with the lens 12 in high, looking up across the field at the HIVE.**

| | First draft (before the tag term; recomputed for red at +X) | Now (both lens options) |
|---|---|---|
| A (`cam0`) | (+78, +65) lens 36 in, 63 deg off the sticker normal | **(-36, +78) lens 30 in, 54 deg** |
| B (`cam1`) | (-65, +78) lens 36 in, 64 deg off the sticker normal | **(+36, +78) lens 12 in, 34 deg** |
| Printed kit tags readable | 2 of 4 | 4 of 4 (Option A lens), 3 of 4 (Option B lens) |
| Mean triangulation angle | 117 deg | 62 deg: at the lower limit, see section 6 |
| Sample ball arcs seen by both | 91 % to 93 % | 92 % (Option A) / 93 % (Option B) |

## 0. Which camera is which

| Label | App source id | Where it stands | Looks toward |
|---|---|---|---|
| **A** | **`cam0`** | outside the +Y (audience) wall, 36 in left of the center line seen from the field (x = -36), lens 30 in high | across the field toward +X and -Y (away from the audience), tilted up |
| **B** | **`cam1`** | outside the +Y (audience) wall, x = +36, lens 12 in high | across the field toward -X and -Y (away from the audience), tilted up steeply |
| C (optional, exit speed) | `cam2` (not needed for the two-camera pipeline) | outside the +Y wall, x = +13, lens 58 in high | down at the launch zone |

Field axes (same as the app and the 3-D viewer): origin at field center, Z up, **+Y toward the audience**, X along the red/blue axis, **red HIVE at X = +12.75 (the +X half), blue at -12.75**. Standing at the audience wall facing the field, +X (red) is on your **left**. The map is drawn with the audience at the top and +X to the right, so it looks mirrored compared with what you see standing at the audience wall; use the labels and the table below, not "left" and "right". Check once at the field that the red HIVE is the one on your left when you stand at the audience wall (VERIFY: if the real layout is the other way round, mirror every X in this document and tell the developer).

Option A (GoPro over RTMP): publish camera A to `rtmp://<PC-IP>:1935/cam0` and camera B to `.../cam1`. Capture card or USB camera: the device index order is not guaranteed. Wave a hand in front of A and watch which Calibration-tab card (`cam0` or `cam1`) shows it; swap the two source rows in Settings if it is wrong. Never assume the index order.

## 1. Equipment

| | Option A: GoPro (2 + optional 3rd) | Option B: USB global shutter |
|---|---|---|
| Cameras | 2x GoPro HERO12/13 + Media Mod | 2x Arducam 2.3 MP global shutter (USB 2.0) |
| Link | micro-HDMI 10 ft to Cam Link 4K | 16 ft active USB extension, **straight into its own USB port on the PC** (no hub) |
| Power | USB-C wall power (battery ~1 h) | USB bus power from the PC port |
| Mount | tripod or stand that holds the lens at 30 in (A) and 12 in (B) + 1/4-20 adapter | same, + board case |
| Exit-speed camera C | optional 3rd camera (USB Arducam on 16 ft ext.) at 58 in on a 60 in tripod | same, optional 3rd Arducam |
| Also | painter's tape, tape measure, phone level app, plumb line, string, checkerboard and tag kit (see calibration.md) | same |

A lens at 12 in needs a low mount: a short tripod, a clamp on a stool or a camera on a low stand. Keep the lens at or above the top of the field wall so the wall does not appear at the bottom of the picture (VERIFY the wall height on your field).

## 2. Camera positions (inches; tripods are 6 in beyond the INSIDE face of the wall)

Tripod spots are the same for both lens options; only the FOV and a small aim difference apply.

**What the numbers mean.** The coordinates and the "+-72 in" wall are the **inside face** of the perimeter wall (the face the robot sees). A person outside the field can only reach the outside face. The FTC perimeter wall is assumed to be **1.5 in thick (VERIFY with a tape on your wall and use the real number)**. So:

- Distance from the **outside face** to the lens = 6 in (clearance from the inside face) minus the wall thickness = **4.5 in** for a 1.5 in wall (in general 6 - t).
- The lens position is the spot **under the lens** (drop a plumb line from the lens). The tripod feet are not the reference; draw the foot triangle around the plumb spot.
- Distance along a wall is measured **parallel to the wall from the outer edge of the adjacent perpendicular wall** (the corner): inside-face distance + wall thickness 1.5 in. A and B: 36 + 1.5 = **37.5 in**. C: 59 + 1.5 = **60.5 in**.

| Cam | App id | Role | From field center (x, y) | Lens height | Tape: out from the OUTSIDE face / along the wall from the corner's outer edge | Aim, Option A (GoPro): yaw / pitch / aim point | Aim, Option B (Arducam): yaw / pitch / aim point |
|---|---|---|---|---|---|---|---|
| A | `cam0` | primary | (-36, +78) | 30 in | 4.5 in out from the +Y wall; 37.5 in along it from the -X wall's outer edge (corner (-72,+72) on the inside face) | **316 deg**, **+21 deg** up, (+11, +32, 55) | **318 deg**, **+23 deg** up, (+12, +35, 58) |
| B | `cam1` | primary | (+36, +78) | 12 in | 4.5 in out from the +Y wall; 37.5 in along it from the +X wall's outer edge (corner (+72,+72) on the inside face) | **239 deg**, **+43 deg** up, (+11, +36, 58) | **240 deg**, **+45 deg** up, (+12, +37, 59) |
| C | `cam2` | exit speed (optional) | (+13, +78) | 58 in | 4.5 in out from the +Y wall; 60.5 in along it from the +X wall's outer edge | 269 deg, -45 deg down, (+12.75, +50, 30) the launch zone | same |

Yaw is a bearing in **field coordinates**: 0 deg = toward +X, 90 deg = toward +Y (the audience), 180 deg = toward -X, 270 deg = toward -Y. A (316 deg) looks across the field toward +X and -Y; B (239 deg) looks toward -X and more toward -Y. A phone compass is useless indoors; use the aiming method below.

**Aiming method (no software, about 2 minutes per camera).**

1. **Floor mark.** Put a tape cross on the field floor at the (x, y) of the camera's aim point in the table: **A (+11, +32)** and **B (+11, +36)** for Option A, **A (+12, +35)** and **B (+12, +37)** for Option B (about 11 in from the center line on the red side, 32 to 37 in toward the audience from field center, i.e. about 17 to 21 in in front of the up CELL, toward the audience). It is the point on the floor straight below the aim point.
2. **Yaw.** Stretch a string from the plumb spot under the lens to the cross, or sight over the lens, and turn the tripod head until the lens points along the string. Tolerance about 3 deg.
3. **Pitch and roll.** Lay a phone with a level app on top of the camera body (or use the tripod's own level). Set the pitch from the table, +-2 deg. Roll must read 0 deg, +-1 deg.
4. **Check in the app preview** (Calibration tab, **Refresh image**). This is the real acceptance test:
   - The **up-CELL opening** (the tilted 20 in wide opening of the red HIVE nearest the audience) is in the middle area: its center at about **57 % from the left and 50 % from the top** in A (58 / 54 for the Arducam), and about **42 % from the left and 62 % from the top** in B (43 / 62).
   - The **four AprilTags under the up CELL** (ids 34 to 37) are visible in both pictures as a short row of small squares just below the opening: A at about 55 to 62 % across and 60 to 63 % down; B at about 36 to 45 % across and 72 to 76 % down (GoPro; the Arducam is within 3 %).
   - The **four printed kit tags**, if taped on (calibration.md), are at about: A: 100 at 80/31, 101 at 50/50, 102 at 89/47, 103 at 63/58; B: 100 at 62/69, 101 at 37/53, 102 at 50/84, 103 at 29/74 (percent from left / from top, GoPro; the Arducam is within 5 %).
   - **All 8 calibration points are visible, at least 20 px inside the image edge** (the four corners of that opening and the four top corners of the HIVE frame; calibration.md shows where each appears). The aim table was centered in the range that keeps the tags and points in view: it stays true if the camera is off by up to **3 deg in yaw or pitch** (computed minimum slack: A 5 deg of yaw, B 6 deg of pitch up). Aim within 3 deg anyway, and if a tag or point is cut off, turn the camera back toward the table value.
   - The **launch area is below the bottom edge of the picture, on purpose**: the cameras look up at the HIVE, and the ball flies up into view from the bottom edge. Do not tilt down to get the launch zone in frame.

   The extrinsic calibration measures each camera's true pose, so the tolerances above are about keeping the 8 points, the tags and the ball paths in frame, not about hitting the table values to the degree.
5. **In-frame roll check.** The frame's audience-side top bar (calibration points 5 and 6) is **not** level in the picture: it runs along the line of sight, so perspective tilts it. With the camera leveled it looks like this: in A it runs from the upper right down to the lower left, about **21 deg below horizontal** (for every 100 px it moves left it drops about 38 px); in B it runs from the lower right up to the upper left, about **20 deg above horizontal** (100 px left, 36 px up). If the bar's slope differs from this by more than about 3 deg, the camera is rolled or aimed wrong: re-check the level and the yaw.

Aim point: the middle of the image is on the aim point in the table (about 55 to 59 in high).

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
3. Set each tripod so the lens is at the height in the table (30 in for A, 12 in for B). Lens centered over the tape cross (plumb line).
4. Put the floor crosses on the field and aim each camera with the aiming method in section 2: yaw by string, pitch and roll with the level app.
5. Check the preview against section 2 step 4 and step 5. All 8 calibration points and the four CELL tags must be visible.
6. Cable: run all cables along the floor outside the wall, tape them down, and keep them out of the tripod legs. **Option B (two USB 2.0 Arducam cameras): each camera, through its own extension, goes directly into its own USB port on the PC.** Two cameras must not share one hub link (no hub, powered or not, between a camera and the PC): two 1080p90 MJPEG streams starve a single USB 2.0 hub link and fps drops. If front-panel ports share one internal hub, use one front and one rear port, then confirm fps in the app. Option A: each Cam Link into its own USB 3 port.
7. Open the app preview (Calibration tab). Confirm in `cam0` (A) and `cam1` (B) that the CELL opening, the CELL tags and all 8 reference points are in frame and that the ball path will enter from the bottom edge.
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
- [ ] Calibration error under 2 px at every one of the 8 points or with the tag kit (calibration.md); a test ball ends its track at the CELL opening.
- [ ] Ball test: throw 3 balls; each is tracked in both cameras for the whole flight.

## 6. Expected numbers (pollen ball, 2.8 in, 1080p; from the simulated sample shots)

| | Option A (86 deg) | Option B (95 deg) |
|---|---|---|
| Ball diameter, cam A | 32 to 114 px (mean 42) | 27 to 99 px (mean 36) |
| Ball diameter, cam B | 32 to 196 px (mean 46) | 28 to 213 px (mean 40) |
| Ball diameter, cam C (first 0.2 s) | 55 to 125 px | 47 to 111 px |
| Mean triangulation angle A/B | 62 deg (target 60 to 120) | 62 deg |
| Sample points seen by both A and B | 92 % | 93 % |
| Points where the HIVE frame blocks a ray | 2 % | 2 % |
| Angle to the CELL sticker normal, A / B | 54 / 34 deg (readable under 55) | 54 / 34 deg |
| Shortest CELL tag edge in the picture, A / B | 30 / 40 px | 26 / 34 px |
| Printed kit tags readable (under 55 deg, edge 28 px or more), A / B | 4 / 4 of 4 | 3 / 3 of 4 |

The triangulation angle is at the lower edge of the 60 to 120 deg band because both cameras are on the same (audience) wall, 72 in apart. Depth accuracy along the line of sight is therefore weaker than with a side-wall layout. If the ball is under 10 px or the angle is outside 60 to 120 deg, the cameras are off their marks. A side-wall layout (one camera on the +X wall, one on the +Y wall, lens 36 in) gives about 117 deg but the CELL tags are not readable from it (63 to 64 deg off the normal); it remains usable if you rely only on the printed tag kit (calibration.md) and set the HIVE state by hand. Sticker angle for A is close to the 55 deg limit: if the CELL tags are not read in A, lower A's lens or move it toward the center line.

## 7. Assumptions

Shots are lobs of 230 in/s from 12 in height, 50 to 66 in from field center along +Y, x within 30 in of the red HIVE; the ball is cut where it crosses the opening. Pinhole camera, no distortion. A tripod head can stand 6 in beyond the inside face of the wall (4.5 in from the outside face for a 1.5 in wall, VERIFY). The CELL tag positions come from the official CAD (`field.hive_tag_corners`, docs/research_apriltags.md): the sticker lies on the CELL floor, 7.19 in behind the opening, facing down and toward the audience. Tag readability is judged by angle (under 55 deg), size and being inside the picture, not by a detection test on a real field (VERIFY with the first footage). Occlusion of the sticker by the CELL rim or the robot is not modeled. The HIVE frame size and top height used for calibration points 5 to 8 and the kit tags are CAD guesses (VERIFY). This is a draft for M1 test footage; finalize after the first footage.

# Camera placement (draft, from `hiveshot/placement.py`)

Map: `docs/camera_placement.png` (same content as `camera_placement.svg`) shows **Option B, the Arducam USB cameras that were purchased** (numbers and title for HFOV 95 deg); the GoPro alternative is `docs/camera_placement_gopro.png` / `.svg`. Top-down, X right, Y up, **audience side (the red up CELL) at the top**. Origin = field center. Wall = +-72 in, the **INSIDE face** of the wall for a field that is 144 in wall to wall (see "Your field" below). Tiles 24 in. The map draws the real frame (CAD A-frame: foot bars, legs, crossbar) and the four printed kit tags (dark bars; 100/101 on the audience logo panel at the crossbar ends, 102/103 standing at the audience-side base corners) and labels the **tag reader** camera. Regenerate: `.venv\Scripts\python.exe -c "from hiveshot import placement as p; p.write_map('usb','docs/camera_placement.svg','docs/camera_placement.png'); p.write_map('gopro','docs/camera_placement_gopro.svg','docs/camera_placement_gopro.png')"`.

All field geometry (CELL opening, tag rows, frame, beams) is read from `hiveshot/field.py`, which follows the official CAD: the red up-CELL opening center is at (+12.75, 15.77, 59.55) and its AprilTag row at (+12.75, 13.10, 49.79). **Red is the +X HIVE, blue the -X HIVE.** The HIVE frame is **not a box**: at each X end an A-frame (a foot bar on the tiles at x = +-24.73, y = +-19.47, legs leaning inward to an apex) and a 24 in crossbar along X at height 41.45 in joining the two apexes (x = +-12.0); the highest point of the frame is the pivot cradles at 44.3 in. An earlier version of this document and of the calibration points used "frame top corners" at 64 in that do not exist; they are gone.

## Your field (measure it)

The numbers below assume a field 144 in wall to wall. The CAD field is 141.35 in between the inside faces of the perimeter glass, and real fields vary. **Measure your field wall to wall (inside face to inside face) and write it down; the app's `field_size` setting defaults to 144 in: set it to your measurement.** All tripod spots are given as tape-measure distances from the wall you can touch (12 in out from the OUTSIDE face of the wall, and so many inches along the wall from a corner); use those, not the (x, y) coordinates, which are only exact for 144 in. Field center is the middle between opposite walls. Check the wall thickness too: **1.5 in is assumed (VERIFY)**; if your wall is thicker, 12 in from the OUTSIDE face is still the rule.

## How the positions were chosen (hard constraints)

`placement.recommend()` searches lens heights 20 to 58 in (the UBeesize MT60's practical minimum is assumed to be 20 in, VERIFY) and aim heights, on a ring outside the wall (plus every 12 in along the audience wall). The recommendation has to satisfy all of these:

1. **Triangulation angle at least 75 deg** (mean over the sample ball arcs; at most 120 deg), and 90 % of the arcs seen by both cameras.
2. **Lens height at least 20 in.**
3. **At least one camera reads the CELL's AprilTags** (the "tag reader"): sticker under 55 deg off its normal, all four tags inside the picture, shortest tag edge at least 20 px, and no robot in the way. The printed kit calibrates both cameras, so one reader is enough for the HIVE state.
4. **The robot does not block the view**: a box 18 x 18 x 24 in (grown by 3 in on every side to allow for an intake or arm) is centered on each sample launch point; rays from the camera to the ball in the first 0.3 s of the flight, to the up-CELL opening center and to the tag row center must be free for at least 90 % of the samples. Ball positions still inside the box are not counted.
5. **The printed kit is readable in both cameras**: at least 3 of the 4 six-inch kit tags under 55 deg off their normal, inside the picture, at least 28 px, and not overlapping the CELL sticker in the picture (the base tags 102 and 103 stand on the tiles, so the cameras must be aimed low enough to see them), and all 8 click calibration points (the corners of the two CELL openings) are in frame (60 px margin).
6. Cameras on the audience wall prefer the corners over the wall center (the drive team stands at the audience wall), and **both cameras on the audience wall are accepted only if nothing else satisfies 1 to 5.** Here nothing else does: a camera on a side wall sees the base tag on the far side of the frame at 64 deg or more and cannot read three kit tags. So **both cameras are on the audience wall, in its two corners.** This is the case the rule allowed; the drive team stands between them.

Triangulation angle, tag reading and kit readability are only judged by geometry, not by a detection test on a real field. One set of tripod spots serves both lens options.

## Recommendation

| | Recommended (Arducam and GoPro) |
|---|---|
| A (`cam0`) | **(-72, +85.5), lens 20 in**, outside the audience wall in the -X corner. Tag angle **57 deg: not a tag reader**; reads all four kit tags (Arducam), all four (GoPro) |
| B (`cam1`) | **(+72, +85.5), lens 20 in**, outside the audience wall in the +X corner. Tag angle **51 deg: the tag reader** (CELL sticker readable); reads all four kit tags (Arducam) or 100, 101, 102 (GoPro) |
| Mean triangulation angle | **97 deg** (both options) |
| Ball arcs seen by both | 97 % (Option A) / 100 % (Option B) |
| Robot-free rays (all samples), A / B | 100 % / 98 %; CELL and tag rays 100 % |
| Both cameras on the audience wall | yes (rule 6: no other pair meets rules 1 to 5) |

The best pair in which BOTH cameras read the CELL's tags (stricter than rule 3) does not exist with the 20 px tag-size rule: A sees the sticker 57 deg off its normal (15.8 to 18.4 px tag edges), so the CELL tags are read by `cam1` only; `cam0` is calibrated from the kit, and the HIVE state comes from `cam1`. The alternative reported by `recommend()` is the same pair.

## 0. Which camera is which

| Label | App source id | Role | Where it stands | Looks toward |
|---|---|---|---|---|
| **A** | **`cam0`** | primary | outside the audience wall in the **-X corner**, lens 20 in | across the field toward +X and -Y (away from the audience), level (pitch +9 to +10 deg) |
| **B** | **`cam1`** | primary and **tag reader** | outside the audience wall in the **+X corner**, lens 20 in | toward -X and -Y, pitch +11 to +13 deg |
| C (optional, exit speed) | `cam2` (not needed for the two-camera pipeline) | exit speed | outside the +Y wall, x = +13, lens 58 in | down at the launch zone |

Field axes (same as the app and the 3-D viewer): origin at field center, Z up, **+Y toward the audience**, X along the red/blue axis, **red HIVE at X = +12.75 (the +X half), blue at -12.75**. Standing at the audience wall facing the field, +X (red) is on your **left**. The map is drawn with the audience at the top and +X to the right, so it looks mirrored compared with what you see standing at the audience wall; use the labels and the table below, not "left" and "right". Check once at the field that the red HIVE is the one on your left when you stand at the audience wall (VERIFY: if the real layout is the other way round, mirror every X in this document and tell the developer).

Option A (GoPro over RTMP): publish camera A to `rtmp://<PC-IP>:1935/cam0` and camera B to `.../cam1`. Capture card or USB camera: the device index order is not guaranteed. Wave a hand in front of A and watch which Calibration-tab card (`cam0` or `cam1`) shows it; swap the two source rows in Settings if it is wrong. Never assume the index order.

## 1. Equipment

| | Option A: GoPro (2 + optional 3rd) | Option B: USB global shutter |
|---|---|---|
| Cameras | 2x GoPro HERO12/13 + Media Mod | 2x Arducam 2.3 MP global shutter (USB 2.0) |
| Link | micro-HDMI 10 ft to Cam Link 4K | 16 ft active USB extension, **straight into its own USB port on the PC** (no hub) |
| Power | USB-C wall power (battery ~1 h) | USB bus power from the PC port |
| Mount | tripod with the lens at 20 in (A and B) + 1/4-20 adapter (UBeesize MT60: lowest practical lens height assumed 20 in, VERIFY) | same, + board case |
| Exit-speed camera C | optional 3rd camera (USB Arducam on 16 ft ext.) at 58 in on a 60 in tripod | same, optional 3rd Arducam |
| Also | painter's tape, tape measure, phone level app, plumb line, string, checkerboard and the 6 in tag kit, 4 pages (see calibration.md), a small stand or card easel for tags 102 and 103 | same |

## 2. Camera positions (inches; the lens is 12 in outside the wall)

Tripod spots are the same for both lens options; only the FOV and a small aim difference apply.

**What the numbers mean.** The coordinates and the "+-72 in" wall are the **inside face** of the perimeter wall (the face the robot sees) for a 144 in field. A person outside the field can only reach the outside face. The FTC perimeter wall is assumed to be **1.5 in thick (VERIFY with a tape on your wall and use the real number)**. So:

- The lens plumb spot is **12 in out from the OUTSIDE face** of the wall (13.5 in from the inside face, which is y = 85.5 in a 144 in field).
- The lens position is the spot **under the lens** (drop a plumb line from the lens).
- Distance along a wall is measured **parallel to the wall from the outer edge of the adjacent perpendicular wall** (the corner): the corner cameras A and B are **1.5 in** from the outer edge of the -X / +X wall (their plumb spot is above the inside face of that side wall). Camera C: 60.5 in along from the +X wall's outer edge.

**Tripod feet (where they go).** A 3-leg tripod stands with **one leg pointing straight away from the wall** (toward the audience side, away from the field) and the other two legs 60 deg either side, pointing toward the wall. With a leg radius of about 20 in at the lens height (center to foot, measure yours with a tape; a lens at 20 in is a low, narrower stance), those two feet are 10 in from the plumb spot toward the wall, so **12 in out from the outside face keeps every foot at least 2 in clear of the wall.** If your tripod's leg radius R is larger, the lens must be at least R/2 + 2 in out from the outside face. Never let a foot rest on or over the wall; mark all three foot spots with tape before you set the tripod, with the plumb spot at the center of the three.

| Cam | App id | From field center (x, y) | Lens height | Tape: out from the OUTSIDE face / along the wall from the corner's outer edge | Aim, Option A (GoPro): yaw / pitch / aim point | Aim, Option B (Arducam): yaw / pitch / aim point | Tag angle (limit 55) |
|---|---|---|---|---|---|---|---|
| A | `cam0` | (-72, +85.5) | 20 in | 12.0 in out from the +Y wall; 1.5 in along it from the -X wall's outer edge (corner (-72,+72) on the inside face) | **327 deg**, **+9 deg** up, (+11, +32, 35) | **329 deg**, **+10 deg** up, (+12, +35, 38) | 57 deg, not a reader |
| B | `cam1` | (+72, +85.5) | 20 in | 12.0 in out from the +Y wall; 1.5 in along it from the +X wall's outer edge (corner (+72,+72) on the inside face) | **215 deg**, **+11 deg** up, (+9, +41, 35) | **218 deg**, **+13 deg** up, (+12, +38, 37) | **51 deg, tag reader** |
| C (optional) | `cam2` | (+13, +85.5) | 58 in | 12.0 in out from the +Y wall; 60.5 in along it from the +X wall's outer edge | 270 deg, -38 deg down, (+12.75, +50, 30) the launch zone | same | n/a |

Yaw is a bearing in **field coordinates**: 0 deg = toward +X, 90 deg = toward +Y (the audience), 180 deg = toward -X, 270 deg = toward -Y. A (327 to 329 deg) looks across the field toward +X and -Y; B (215 to 218 deg) looks toward -X and -Y. A phone compass is useless indoors; use the aiming method below. The aim heights (35 to 38 in) are low on purpose: the kit tags 102 and 103 stand on the tiles at the frame base and must be in the picture, and the whole ball arc stays in view; the CELL openings (53.5 to 65.6 in) are in the upper part of the picture.

**Aiming method (no software, about 2 minutes per camera).**

1. **Floor mark.** Put a tape cross on the field floor at the (x, y) of the camera's aim point in the table: **A (+11, +32)** and **B (+9, +41)** for Option A, **A (+12, +35)** and **B (+12, +38)** for Option B. It is the point on the floor straight below the aim point.
2. **Yaw.** Stretch a string from the plumb spot under the lens to the cross, or sight over the lens, and turn the tripod head until the lens points along the string. Tolerance about 3 deg.
3. **Pitch and roll.** Lay a phone with a level app on top of the camera body (or use the tripod's own level). Set the pitch from the table, +-2 deg. Roll must read 0 deg, +-1 deg.
4. **Check in the app preview** (Calibration tab, **Refresh image**). This is the real acceptance test:
   - The **up-CELL opening** (the tilted 20 in wide opening of the red HIVE nearest the audience) is in the upper part of the picture: its center at about **56 % from the left and 31 % from the top** in A (56 / 36 for the Arducam), and about **37 % from the left and 28 % from the top** in B (41 / 34).
   - The **four AprilTags under the up CELL** (ids 34 to 37) show as a short row of small squares just below the opening: in A at about 55 to 59 % across and 38 to 40 % down (Arducam 56 to 59 % and 42 to 44 %), in B at about 33 to 39 % across and 36 to 39 % down (Arducam 38 to 43 % and 41 to 43 %). In B they are readable (tag edges 22 to 27 px); in A they are seen 57 deg off their normal, too oblique to decode.
   - The **four printed kit tags** (6 in) are at about (percent from the left / from the top, GoPro; the Arducam is within 3 %): A: 100 at 70/47, 101 at 61/50, 102 at 70/87, 103 at 52/79; B: 100 at 42/54, 101 at 33/52, 102 at 50/84, 103 at 32/91. With the Arducam all four are inside the picture in both cameras; with the GoPro tag 103 in B is at 91 % from the top, too close to the bottom edge to count (B then reads 100, 101, 102). Tags 102 and 103 must be in the picture: if one is cut off, tilt the camera down a little.
   - **All 8 calibration points are visible, at least 20 px inside the image edge**: the four corners of the red up-CELL opening and the four corners of the blue far-CELL opening (calibration.md shows where each appears). The aim table is centered in the range that keeps the kit, the points and (for B) the tags in view. It stays true if the camera is off by up to **3 deg in yaw or pitch** (computed minimum slack: 4 deg, B pitch up, for the GoPro; more for the others). Aim within 3 deg, and if a tag or point is cut off, turn the camera back toward the table value.
   - The **launch area is mostly outside the picture, on purpose**: the ball flies into view early in the flight. Do not tilt up to get the CELL high in frame at the cost of the base tags.

   The extrinsic calibration measures each camera's true pose, so the tolerances above are about keeping the 8 points, the tags and the ball paths in frame, not about hitting the table values to the degree.
5. **In-frame roll check.** Tags 100 and 101 are on the same horizontal line of the logo panel 24 in apart, so the line through their centers is horizontal in the field but **not** in the picture (perspective). With the camera leveled it looks like this: in A it runs from tag 100 (right) to tag 101 (left) and drops about 18 px per 100 px going left (about 10 deg below horizontal); in B it rises about 17 px per 100 px going left (about 10 deg above horizontal). If the slope differs from this by more than about 3 deg, the camera is rolled or aimed wrong: re-check the level and the yaw.

Aim point: the middle of the image is on the aim point in the table (35 to 41 in high).

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

1. Clear the field (no robot, nobody inside the walls). Set the HIVE in its match-start state: red HIVE audience CELL up, blue HIVE far CELL up.
2. Measure the field wall to wall, set the app's `field_size`, and measure the wall thickness. From the corner named in the table, measure along the wall (from the outer corner edge), then out from the **outside face** of the wall (**12.0 in**). Mark the plumb spot with a painter's tape cross and the three tripod feet around it (one foot straight away from the wall, section 2). Label it A, B, C and write the app id (`cam0`, `cam1`) next to it.
3. Set each tripod so the lens is at 20 in (A and B). Lens centered over the tape cross (plumb line).
4. Put the floor crosses on the field and aim each camera with the aiming method in section 2: yaw by string, pitch and roll with the level app.
5. Check the preview against section 2 step 4 and step 5. All 8 calibration points and the four kit tags must be visible; the four CELL tags must be readable in `cam1`.
6. Cable: run all cables along the floor outside the wall, tape them down, and keep them out of the tripod legs. **Option B (two USB 2.0 Arducam cameras): each camera, through its own extension, goes directly into its own USB port on the PC.** Two cameras must not share one hub link (no hub, powered or not, between a camera and the PC): two 1080p90 MJPEG streams starve a single USB 2.0 hub link and fps drops. If front-panel ports share one internal hub, use one front and one rear port, then confirm fps in the app. Option A: each Cam Link into its own USB 3 port.
7. Open the app preview (Calibration tab). Confirm in `cam0` (A) and `cam1` (B) that the CELL openings and the kit tags are in frame.
8. Run the calibration (docs/calibration.md). Write the date next to the tape marks. Keep the drive team's station away from the corner tripods and keep people out of the line between each camera and the HIVE.

## 5. Pre-session checklist

- [ ] Field measured wall to wall, `field_size` set, wall thickness checked.
- [ ] Tripod feet on tape (one leg pointing away from the wall, no foot over the wall), legs locked, camera tight on its mount.
- [ ] Lens height, yaw and pitch match the table; level app reads roll 0; HyperSmooth OFF; Linear lens (Option A).
- [ ] `cam0` is A and `cam1` is B (hand in front of A shows on the `cam0` card).
- [ ] Option B: the two cameras are in two different PC ports, no hub.
- [ ] Focus locked at the HIVE (Option B). Lens clean.
- [ ] Batteries topped up or USB-C power connected (Option A).
- [ ] All cameras show live video at the expected fps (60 / 90) with no dropped frames.
- [ ] Lighting: no window or bright light **behind** the HIVE (it silhouettes the ball). Light from above or from the audience side is best. Keep the orange/yellow ball in even light.
- [ ] Kit tags taped on and **each tag's position tape-measured to within 0.25 in** (calibration.md), then the calibration error is under 2 px and the Cross-check button shows green (under 1 in).
- [ ] Ball test: throw 3 balls; each is tracked in both cameras for the whole flight.

## 6. Expected numbers (pollen ball, 2.8 in, 1080p; from the simulated sample shots)

| | Option A (86 deg) | Option B (95 deg) |
|---|---|---|
| Ball diameter, cam A | 24 to 53 px (mean 29) | 20 to 45 px (mean 25) |
| Ball diameter, cam B | 29 to 87 px (mean 37) | 24 to 76 px (mean 31) |
| Ball diameter, cam C (first 0.2 s) | 51 to 98 px | 44 to 86 px |
| Mean triangulation angle A/B | 97 deg (hard limit 75 to 120) | 97 deg |
| Sample points seen by both A and B | 97 % | 100 % |
| Points where the HIVE frame blocks a ray | 0 % | 0 % |
| Rays free of the robot (box 18 x 18 x 24 in + 3 in), A / B | 100 % / 98 % | 100 % / 98 % |
| Angle to the CELL sticker normal, A / B | 57 / 51 deg (B reads the tags) | 57 / 51 deg |
| Shortest CELL tag edge in the picture, B | 27 px | 22 px |
| Printed kit tags (6 in) readable (under 55 deg, 28 px or more, not over the sticker), A / B | 4 / 3 of 4 | 4 / 4 of 4 |
| Pose from the kit with exact taping (synthetic, noise and blur), max | 0.14 in / 0.10 deg | 0.21 in / 0.11 deg |

If the ball is under 10 px or the triangulation angle is outside 75 to 120 deg, the cameras are off their marks. The robot box is a model: even with a 12 in extension B still has 92 % free rays (A 98 %); a robot bigger than 24 x 24 in or the drive team standing in the line of `cam1` will leave gaps in the tracks.

**What taping error does** (kit solve, this placement, 20 synthetic runs per case, Arducam; GoPro the same within 0.2 in; evidence/refute/dod9_kit_mounting_sim.json): each tag displaced by the error vector and rotated by the angle error, the solver still using the model positions:

| Tag mounting error | Camera position error (median / max) | Rotation error (median / max) | Reprojection RMSE the app shows | Runs under 2 px | Up-CELL opening center error (median / max) |
|---|---|---|---|---|---|
| exact | 0.14 / 0.21 in | 0.08 / 0.11 deg | 0.8 px | 20 / 20 | 0.04 / 0.04 in |
| 0.25 in, 0.5 deg | 1.0 / 2.0 in | 0.55 / 1.0 deg | 1.0 px | 20 / 20 | 0.28 / 0.54 in |
| 0.5 in, 1 deg | 2.1 / 4.1 in | 1.1 / 2.0 deg | 1.7 px | 9 / 20 | 0.51 / 1.1 in |
| 1 in, 2 deg | 4.2 / 8.0 in | 2.0 / 3.9 deg | 3.2 px | 0 / 20 | 1.1 / 2.3 in |

The camera pose follows the taping error, so **each tag's position must be tape-measured to within 0.25 in (and its tilt to 0.5 deg) before calibrating.** With 0.5 in the 2 px gate already fails in most runs and with 1 in it always does.

## 7. Assumptions

Shots are lobs of 230 in/s from 12 in height, 50 to 66 in from field center along +Y, x within 30 in of the red HIVE; the ball is cut where it crosses the opening. The robot is a box 18 x 18 x 24 in on the floor centered on the launch point, plus 3 in of extension on every horizontal side; occlusion by people or the audience barrier is not modeled. Pinhole camera, no distortion. The tripod leg radius (about 20 in at the lens height) and the UBeesize MT60's 20 in minimum lens height are assumptions (VERIFY). A 144 in field with 1.5 in walls; see "Your field". The CELL tag positions come from the official CAD (`field.hive_tag_corners`, docs/research_apriltags.md): the sticker lies on the CELL floor, 7.19 in behind the opening, facing down and toward the audience. The frame is the CAD A-frame (`field.frame_reference_points`, the "Frame (CAD-extracted)" constants); the logo panels (y 1.55 to 4.28 in, x +-15.07, z 34.07 to 40.02) are why the crossbar tags are taped on the panel face and not hung from the 1 in crossbar. Tag readability is judged by angle (under 55 deg), size and being inside the picture, not by a detection test on a real field (VERIFY with the first footage). Occlusion of the sticker by the CELL rim is not modeled; during calibration the field is empty, so robots do not block the base tags.

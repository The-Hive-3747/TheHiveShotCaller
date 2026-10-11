# Camera placement (draft, from `hiveshot/placement.py`)

Map: `docs/camera_placement.png` (same content as `camera_placement.svg`) shows **Option B, the Arducam USB cameras that were purchased** (numbers and title for HFOV 95 deg); the GoPro alternative is `docs/camera_placement_gopro.png` / `.svg`. Top-down, X right, Y up, **audience side (the red up CELL) at the top**. Origin = field center. Wall = +-72 in, which is the **INSIDE face** of the wall (see section 2). Tiles 24 in. The map draws the printed kit tags 100 to 103 (dark squares at the frame top corners; dashed squares 104 and 105 are the optional bar tags) and labels the **tag reader** camera (CAM B). Regenerate: `.venv\Scripts\python.exe -c "from hiveshot import placement as p; p.write_map('usb','docs/camera_placement.svg','docs/camera_placement.png'); p.write_map('gopro','docs/camera_placement_gopro.svg','docs/camera_placement_gopro.png')"`.

All field geometry (CELL opening, tag rows, frame, beams) is read from `hiveshot/field.py`, which follows the official CAD: the red up-CELL opening center is at (+12.75, 15.77, 59.55) and its AprilTag row at (+12.75, 13.10, 49.79). **Red is the +X HIVE, blue the -X HIVE.**

## How the positions were chosen (hard constraints)

`placement.recommend()` searches lens heights 20 to 58 in and tripod spots on a ring just outside the wall (plus every 12 in along the audience wall). The recommendation has to satisfy all of these:

1. **Triangulation angle at least 75 deg** (mean over the sample ball arcs; at most 120 deg), and 90 % of the arcs seen by both cameras.
2. **Lens height at least 20 in** (practical minimum of the UBeesize MT60 tripod).
3. **At least one camera reads the CELL's AprilTags** (the "tag reader"): sticker under 55 deg off its normal, all four tags inside the picture, shortest tag edge at least 14 px, and no robot in the way. The printed kit calibrates both cameras, so one reader is enough for the HIVE state; two is preferred but never traded against the triangulation angle.
4. **The robot does not block the view**: a box 18 x 18 x 24 in (grown by 3 in on every side to allow for an intake or arm) is centered on each sample launch point; rays from the camera to the ball in the first 0.3 s of the flight, to the up-CELL opening center and to the tag row center must be free for at least 90 % of the samples. Ball positions still inside the box are not counted.
5. The printed kit is readable in both cameras: at least 3 of the 4 kit tags (6 in tags, see calibration.md) under 55 deg off their normal and at least 28 px (smaller or more oblique tags were lost in compressed video in the synthetic tests; with 4 in tags only 2 per camera were readable), and all 8 click calibration points are in frame (60 px margin).
6. Cameras on the audience wall prefer the corners over the wall center (the drive team stands at the audience wall), and **both cameras on the audience wall are accepted only if nothing else satisfies 1 to 5.** Something else does, so the recommendation has one camera on the audience wall corner and one on the side wall.

One set of tripod spots serves both lens options.

## Recommendation, and the best "both cameras read the tags" alternative

| | **Recommended** | Best alternative with BOTH cameras reading the tags (not recommended) |
|---|---|---|
| A (`cam0`) | **(-78, +65), lens 30 in**, outside the -X wall near the audience corner. Tag angle **66 deg: not a tag reader** (reads kit tags 100, 102, 103) | (-48, +78), lens 20 in, on the audience wall. Tag angle 52 deg (readable) |
| B (`cam1`) | **(+65, +78), lens 20 in**, outside the audience wall in the +X corner. Tag angle **49 deg: the tag reader** (reads kit tags 101, 102, 103) | (+72, +78), lens 20 in. Tag angle 51 deg (readable) |
| Mean triangulation angle | **105 deg** (Option A) / 106 deg (Option B) | 91 deg (Option A) / 91 deg (Option B) |
| Ball arcs seen by both | 93 % / 94 % | 94 % / 96 % |
| Robot-free rays (all samples), A / B | 100 % / 97 %; CELL and tag rays 100 % | 98 % / 98 % |
| Both cameras on the audience wall | no | yes (excluded by rule 6) |

The alternative also meets 75 deg, but it puts both cameras on the audience wall in front of the drive team and has a 14 deg smaller triangulation angle; it is reported for comparison and is not the recommendation. For reference, the first draft (A (+78, +65) and B (-65, +78), lens 36 in) had 63 deg and 64 deg to the sticker normal and could not read the tags. A camera that is not a tag reader still sees the sticker as small squares; the app uses the tag reader (`cam1`, B) for state and the kit for calibration.

## 0. Which camera is which

| Label | App source id | Role | Where it stands | Looks toward |
|---|---|---|---|---|
| **A** | **`cam0`** | primary, wide base | outside the -X wall, near the audience (+Y) corner, lens 30 in | across the field toward +X (a little toward -Y), tilted up 16 deg |
| **B** | **`cam1`** | primary and **tag reader** | outside the audience (+Y) wall, in the +X corner, lens 20 in | toward -X and -Y, tilted up 31 deg |
| C (optional, exit speed) | `cam2` (not needed for the two-camera pipeline) | exit speed | outside the +Y wall, x = +13, lens 58 in | down at the launch zone |

Field axes (same as the app and the 3-D viewer): origin at field center, Z up, **+Y toward the audience**, X along the red/blue axis, **red HIVE at X = +12.75 (the +X half), blue at -12.75**. Standing at the audience wall facing the field, +X (red) is on your **left**. The map is drawn with the audience at the top and +X to the right, so it looks mirrored compared with what you see standing at the audience wall; use the labels and the table below, not "left" and "right". Check once at the field that the red HIVE is the one on your left when you stand at the audience wall (VERIFY: if the real layout is the other way round, mirror every X in this document and tell the developer).

Option A (GoPro over RTMP): publish camera A to `rtmp://<PC-IP>:1935/cam0` and camera B to `.../cam1`. Capture card or USB camera: the device index order is not guaranteed. Wave a hand in front of A and watch which Calibration-tab card (`cam0` or `cam1`) shows it; swap the two source rows in Settings if it is wrong. Never assume the index order.

## 1. Equipment

| | Option A: GoPro (2 + optional 3rd) | Option B: USB global shutter |
|---|---|---|
| Cameras | 2x GoPro HERO12/13 + Media Mod | 2x Arducam 2.3 MP global shutter (USB 2.0) |
| Link | micro-HDMI 10 ft to Cam Link 4K | 16 ft active USB extension, **straight into its own USB port on the PC** (no hub) |
| Power | USB-C wall power (battery ~1 h) | USB bus power from the PC port |
| Mount | tripod with the lens at 30 in (A) and 20 in (B) + 1/4-20 adapter (UBeesize MT60: lowest practical lens height 20 in) | same, + board case |
| Exit-speed camera C | optional 3rd camera (USB Arducam on 16 ft ext.) at 58 in on a 60 in tripod | same, optional 3rd Arducam |
| Also | painter's tape, tape measure, phone level app, plumb line, string, checkerboard and the 6 in tag kit, 4 pages (see calibration.md) | same |

## 2. Camera positions (inches; tripods are 6 in beyond the INSIDE face of the wall)

Tripod spots are the same for both lens options; only the FOV and a small aim difference apply.

**What the numbers mean.** The coordinates and the "+-72 in" wall are the **inside face** of the perimeter wall (the face the robot sees). A person outside the field can only reach the outside face. The FTC perimeter wall is assumed to be **1.5 in thick (VERIFY with a tape on your wall and use the real number)**. So:

- Distance from the **outside face** to the lens = 6 in (clearance from the inside face) minus the wall thickness = **4.5 in** for a 1.5 in wall (in general 6 - t).
- The lens position is the spot **under the lens** (drop a plumb line from the lens). The tripod feet are not the reference; draw the foot triangle around the plumb spot.
- Distance along a wall is measured **parallel to the wall from the outer edge of the adjacent perpendicular wall** (the corner): inside-face distance 7 in + wall thickness 1.5 in = **8.5 in** for A and B (C: 59 + 1.5 = **60.5 in**).

| Cam | App id | From field center (x, y) | Lens height | Tape: out from the OUTSIDE face / along the wall from the corner's outer edge | Aim, Option A (GoPro): yaw / pitch / aim point | Aim, Option B (Arducam): yaw / pitch / aim point | Tag angle (limit 55) |
|---|---|---|---|---|---|---|---|
| A | `cam0` | (-78, +65) | 30 in | 4.5 in out from the -X wall; 8.5 in along it from the +Y wall's outer edge (corner (-72,+72) on the inside face) | **340 deg**, **+16 deg** up, (+12, +32, 58) | **343 deg**, **+16 deg** up, (+13, +37, 58) | 66 deg, not a reader |
| B | `cam1` | (+65, +78) | 20 in | 4.5 in out from the +Y wall; 8.5 in along it from the +X wall's outer edge (corner (+72,+72) on the inside face) | **218 deg**, **+31 deg** up, (+13, +37, 60) | **218 deg**, **+31 deg** up, (+13, +37, 60) | **49 deg, tag reader** |
| C (optional) | `cam2` | (+13, +78) | 58 in | 4.5 in out from the +Y wall; 60.5 in along it from the +X wall's outer edge | 269 deg, -45 deg down, (+12.75, +50, 30) the launch zone | same | n/a |

Yaw is a bearing in **field coordinates**: 0 deg = toward +X, 90 deg = toward +Y (the audience), 180 deg = toward -X, 270 deg = toward -Y. A (340 to 343 deg) looks across the field toward +X and a little toward -Y; B (218 deg) looks toward -X and -Y. A phone compass is useless indoors; use the aiming method below.

**Aiming method (no software, about 2 minutes per camera).**

1. **Floor mark.** Put a tape cross on the field floor at the (x, y) of the camera's aim point in the table: **A (+12, +32)** for Option A or **A (+13, +37)** for Option B, and **B (+13, +37)** for both. It is the point on the floor straight below the aim point.
2. **Yaw.** Stretch a string from the plumb spot under the lens to the cross, or sight over the lens, and turn the tripod head until the lens points along the string. Tolerance about 3 deg.
3. **Pitch and roll.** Lay a phone with a level app on top of the camera body (or use the tripod's own level). Set the pitch from the table, +-2 deg. Roll must read 0 deg, +-1 deg.
4. **Check in the app preview** (Calibration tab, **Refresh image**). This is the real acceptance test:
   - The **up-CELL opening** (the tilted 20 in wide opening of the red HIVE nearest the audience) is near the middle: its center at about **58 % from the left and 50 % from the top** in A (59 / 50 for the Arducam), and about **40 % from the left and 58 % from the top** in B (41 / 57).
   - The **four AprilTags under the up CELL** (ids 34 to 37) show as a short row of small squares just below the opening: in A at about 57 to 61 % across and 58 to 60 % down (Arducam 59 to 62 % and 57 to 59 %), in B at about 35 to 41 % across and 66 to 70 % down (Arducam 37 to 43 % and 64 to 67 %). In B they are readable; in A they are seen too obliquely (66 deg) to decode.
   - The **four printed kit tags** (6 in), if taped on (calibration.md), are at about (percent from the left / from the top, GoPro; the Arducam is within 5 %): A: 100 at 67/37, 101 at 54/51, 102 at 87/43, 103 at 69/54; B: 100 at 54/66, 101 at 37/51, 102 at 41/73, 103 at 24/63. Each camera reads three of them reliably (A: 100, 102, 103; B: 101, 102, 103; the rest are too oblique). Tags 102 and 103 are on the far-side top bar and can be partly hidden behind the CELL in these views (not modeled); if one is hidden, Auto-calibrate uses the remaining ones and `cam1` adds the CELL tags. Optional tags 104 and 105 on the audience-side top bar (midpoint -12 / +12 in) give `cam1` a fourth readable tag (calibration.md).
   - **All 8 calibration points are visible, at least 20 px inside the image edge** (the four corners of that opening and the four top corners of the HIVE frame; calibration.md shows where each appears). The aim table is centered in the range that keeps the kit, the points and (for B) the tags in view. It stays true if the camera is off by up to **3 deg in yaw or pitch** (computed minimum slack: 5 deg, A yaw toward +X, for the GoPro; more for the others). Aim within 3 deg, and if a tag or point is cut off, turn the camera back toward the table value.
   - The **launch area is mostly outside the picture, on purpose**: the cameras look up at the HIVE, and the ball flies into view early in the flight. Do not tilt down to get the launch zone in frame.

   The extrinsic calibration measures each camera's true pose, so the tolerances above are about keeping the 8 points, the tags and the ball paths in frame, not about hitting the table values to the degree.
5. **In-frame roll check.** The frame's audience-side top bar (calibration points 5 and 6) is **not** level in the picture: it runs along the line of sight, so perspective tilts it. With the camera leveled it looks like this: in A it runs from the upper right down to the lower left, about **34 deg below horizontal** (for every 100 px it moves left it drops about 68 to 70 px); in B it runs from the lower right up to the upper left, about **28 deg above horizontal** (100 px left, 54 px up). If the bar's slope differs from this by more than about 3 deg, the camera is rolled or aimed wrong: re-check the level and the yaw.

Aim point: the middle of the image is on the aim point in the table (55 to 60 in high).

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
3. Set each tripod so the lens is at the height in the table (30 in for A, 20 in for B). Lens centered over the tape cross (plumb line).
4. Put the floor crosses on the field and aim each camera with the aiming method in section 2: yaw by string, pitch and roll with the level app.
5. Check the preview against section 2 step 4 and step 5. All 8 calibration points must be visible; the four CELL tags must be readable in `cam1`.
6. Cable: run all cables along the floor outside the wall, tape them down, and keep them out of the tripod legs. **Option B (two USB 2.0 Arducam cameras): each camera, through its own extension, goes directly into its own USB port on the PC.** Two cameras must not share one hub link (no hub, powered or not, between a camera and the PC): two 1080p90 MJPEG streams starve a single USB 2.0 hub link and fps drops. If front-panel ports share one internal hub, use one front and one rear port, then confirm fps in the app. Option A: each Cam Link into its own USB 3 port.
7. Open the app preview (Calibration tab). Confirm in `cam0` (A) and `cam1` (B) that the CELL opening and all 8 reference points are in frame.
8. Run the calibration (docs/calibration.md). Write the date next to the tape marks. Keep the drive team's station away from `cam1` (it is in the audience-wall corner) and keep people out of the line between each camera and the HIVE.

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
| Ball diameter, cam A | 24 to 54 px (mean 30) | 21 to 47 px (mean 25) |
| Ball diameter, cam B | 29 to 114 px (mean 38) | 25 to 97 px (mean 33) |
| Ball diameter, cam C (first 0.2 s) | 55 to 125 px | 47 to 111 px |
| Mean triangulation angle A/B | 105 deg (hard limit 75 to 120) | 106 deg |
| Sample points seen by both A and B | 93 % | 94 % |
| Points where the HIVE frame blocks a ray | 4 % | 4 % |
| Rays free of the robot (box 18 x 18 x 24 in + 3 in), A / B | 100 % / 97 % | 100 % / 97 % |
| Angle to the CELL sticker normal, A / B | 66 / 49 deg (B reads the tags) | 66 / 49 deg |
| Shortest CELL tag edge in the picture, B | 29 px | 25 px |
| Printed kit tags (6 in) readable (under 55 deg, 28 px or more), A / B | 3 / 3 of 4 (A: 100, 102, 103; B: 101, 102, 103) | 3 / 3 of 4 |
| Pose from the readable kit tags (synthetic, 0.5 px class noise), A / B | within 0.21 in / 0.13 in and 0.05 / 0.07 deg | within 0.12 in / 0.21 in and 0.13 / 0.05 deg |

If the ball is under 10 px or the triangulation angle is outside 75 to 120 deg, the cameras are off their marks. The robot box is a model: with a 6 in extension B still has 95 % free rays, with 9 in it drops to 86 % (the CELL and tag rays are then blocked from some launch points). If your robot is bigger than 24 x 24 in (including intake) or the drive team stands in the line of `cam1`, expect gaps in the tracks and consider the alternative.

## 7. Assumptions

Shots are lobs of 230 in/s from 12 in height, 50 to 66 in from field center along +Y, x within 30 in of the red HIVE; the ball is cut where it crosses the opening. The robot is a box 18 x 18 x 24 in on the floor centered on the launch point, plus 3 in of extension on every horizontal side; occlusion by people or the audience barrier is not modeled. Pinhole camera, no distortion. A tripod head can stand 6 in beyond the inside face of the wall (4.5 in from the outside face for a 1.5 in wall, VERIFY). The CELL tag positions come from the official CAD (`field.hive_tag_corners`, docs/research_apriltags.md): the sticker lies on the CELL floor, 7.19 in behind the opening, facing down and toward the audience. Tag readability is judged by angle (under 55 deg), size and being inside the picture, not by a detection test on a real field (VERIFY with the first footage). Occlusion of the sticker by the CELL rim is not modeled. The HIVE frame size and top height used for calibration points 5 to 8 and the kit tags are CAD guesses (VERIFY). This is a draft for M1 test footage; finalize after the first footage.

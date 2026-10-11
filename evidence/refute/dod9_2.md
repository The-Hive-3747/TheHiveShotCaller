# Refutation report dod9_2 (DoD 9, round 2)

Claim: "A camera placement map and placement instructions exist in the project folder, and a fresh setup following them yields calibration within the M1 accuracy target" (reprojection under 2 px per camera; the up-CELL opening center triangulates within 1 in of its CAD value).

**VERDICT: REFUTED.** The map, the document and every number in them are internally consistent, and in an idealized simulation the numbers hold. But the kit-tag procedure and calibration points 5 to 8 refer to HIVE frame "top corners" at (+-24.73, +-19.475, 63.95) that do not exist on the official field (the official CAD frame is an A-frame whose highest point is 44.3 in). A fresh setup cannot follow the calibration steps as written, and the accuracy numbers only apply to a world that is not the real one. Secondary findings below (tag mounting tolerance vs the 2 px gate, stale PURCHASE_LIST, tripod footprint, MT60 minimum height unverified).

All scripts and raw outputs: `evidence/refute/dod9_2/` (read-only on source; nothing outside that folder written; no webcam, no servers, no installs). Run with `PYTHONPATH=. .venv\Scripts\python.exe <script>` from the project root. Source tests `tests/test_calib.py tests/test_placement.py tests/test_tagkit.py` pass (re-run by me, `-p no:cacheprovider`).

## 1. Consistency: NOT refuted

- Regenerated all four map files with `placement.write_map('usb'|'gopro', ...)` into `evidence/refute/dod9_2/regen/`. SHA256 identical to `docs/camera_placement.svg` (fa6e8a82...), `.png` (20e395f1...), `_gopro.svg` (a0065e6c...), `_gopro.png` (be08cbe6...).
- `recommend('usb')` and `('gopro')` equal the md table: A (-78,+65) lens 30, B (+65,+78) lens 20, C (+13,+78) lens 58; yaw 342.9 / 339.9 (A), 218.3 (B), 269.5 (C); pitch 16.4 / 16.3, 31.1, -45.0; aim points (13,37,58) / (12,32,58), (13,37,60), (12.75,50,30); wall tape numbers 6.0 / 7.0 from the inside face = 4.5 / 8.5 from the outside face for a 1.5 in wall (C: 59 / 60.5). Triangulation 104.9 / 105.6 deg, both-seen 93.0 / 94.3 %, robot-free A/B 100 / 97 %, frame-blocked 4.1 %, alternative pair (-48,78) / (72,78) at 91 deg with tag angles 51.6 / 51.1, tag angles 66.1 (A) and 48.8 (B), ball pixel ranges and means, kit tag readability lists (A 100,102,103; B 101,102,103). All match.
- Image-percent tables in camera_placement.md and calibration.md (CELL center, CELL tag row, kit tags, 8 points, bar slopes 34 deg / 28 deg and the 68-70 / 54 px per 100 px) recomputed in `check_pct.py` -> `check_pct.txt`: all match to the 1 % printed.
- Doc staleness found elsewhere (see section 4): PURCHASE_LIST.md step 3 still says lens 36 in for both cameras.

## 2. Operator simulation (30 seeds, 1920x1080, pure library): idealized world passes, realistic mounting does not

Script `sim.py` (outputs `sim_usb.txt/json`, `sim_gopro.txt/json`, `agg.txt`). For each seed: VirtualCamera at the documented tripod spot with uniform error +-1 in x/y, +-0.5 in lens height, +-2 deg yaw and pitch, +-1 deg roll; kit tags 100-103 (6 in) and the four CELL tags 34-37 rendered into a frame with 2 gray-level noise and blur, detected with the app's `calib.detect_apriltags`, plus 0.5 px Gaussian noise added to each detected corner, solved with the same `solve_extrinsics_from_points(use_ransac=False)` path as `solve_extrinsics_from_tags`; then the up-CELL opening center (12.75, 15.77, 59.55) and the tag row center are projected through the TRUE cameras (0.5 px noise) and triangulated with the ESTIMATED poses. Also ball-flight points (flight RMS = mean error over every 4th point of the 6 sample shots visible in both images). Click methods: 1.5 px noise. Intrinsics exact, no lens distortion, no video compression (not modeled).

World A: tags taped exactly at the model positions (the idealized case the existing tests use). Arducam option, median / p90 / max:

| Method | reproj px (cam0 / cam1 median, max) | opening-center error in | flight RMS in |
|---|---|---|---|
| kit only (3 to 4 tags per cam) | 0.97 / 0.82 (max 1.35) | 0.09 / 0.13 / 0.19 | 0.13 |
| kit + HIVE tags | 0.97 / 0.90 (max 1.23) | 0.07 / 0.13 / 0.15 | 0.11 |
| HIVE tags only | 0.94 / 0.67 (max 1.19); cam pose off 3.6 / 1.8 in median | 0.25 / 0.36 / 0.45 | 1.31 (max 2.6) |
| click 8 points, 1.5 px noise | 1.71 / 1.68 (max 2.41) | 0.26 / 0.44 / 0.45 | 0.41 |
| click 4 CELL corners only | 0.84 / 0.87 (max 2.48) | 0.28 / 0.40 / 0.54 | 0.82 (max 1.5) |
| click 8 CELL corners (red up + blue far-up CELL) | 1.55 / 1.68 (max 2.82) | 0.26 / 0.42 / 0.45 | 0.49 |

GoPro option is the same within 0.1 px / 0.1 in (`sim_gopro.txt`). So at the model's own coordinates, "under 2 px and under 1 in" holds in 30/30 kit runs (kit and kit+HIVE), and 27/30 (Arducam) or 23/30 (GoPro) click-8 runs pass the 2 px RMS gate. Note per-point: calibration.md 3B step 5 requires EVERY point under 2 px; at 1.5 px click noise only 10/60 (Arducam) and 8/60 (GoPro) camera-solves meet that (an operator clicking at 1.5 px sigma will often be told to redo).

Weaknesses even in World A:
- HIVE-only on cam1 uses only 2 CELL tags (34, 35) in all 30 seeds of the no-mounting-error run: poses off 1.5 to 3.8 in, and one GoPro seed (seed 1) flipped to a pose 125 in / 93 deg wrong while reporting 0.80 px reprojection (saved by the app, which only warns "no kit"; min_tags=2 and the calibration.md "3 tags" rule is not enforced). Cam1 also never decodes tag 102 at the nominal pose in the combined scene: 102 overlaps the CELL sticker in the image (cam B pixels (790-823, 726-775) vs tags 36/37 (787-818, 703-743)), so B reads kit 100, 101, 103 and CELL tags 34, 35 only (docs say 101, 102, 103 and all four CELL tags). `nominal_detect.py`, `nominal_detect2.py`.
- The probe point (opening center) sits next to the tags, so it is insensitive to pose error; the ball-flight RMS is the more telling figure, and it grows with every mounting error below.

World B (what a person with a tape measure produces): each kit tag mounted with Gaussian error, solver still uses the model corners. Arducam / GoPro, kit only:
- 0.25 in per axis and 1 deg yaw: reproj under 2 px in both cameras only 23/30 (Arducam), 19/30 (GoPro); kit+HIVE 21/30, 15/30. Opening-center error stays 0.3 in median (<1 in 30/30) but flight RMS 0.64 in median (max 1.2). Camera pose error median 1.0 to 1.5 in.
- 1.0 in per axis and 2 deg: reproj under 2 px in 1/30 and 0/30; opening-center error 1.24 in median (< 1 in only 10/30 and 11/30); flight RMS 2.5 in median (max 4.9), flight max up to 23 in. kit+HIVE keeps the opening center under 1 in (30/30; the CELL tags anchor it) but reprojection fails 30/30.
So the 2 px gate is only passed with tags placed to about 0.2 in of the model on a frame whose dimensions are themselves unverified (next section).

## 3. Geometry truth (against the official CAD and figures)

- CELL: independent recomputation from the STEP (`cad_vs_field.py`, `cad_vs_field.txt`): outer Goal Rib front face z_loc 0.062 plane with the official 53.5 / 65.6 edges gives opening center (12.742, 15.766, 59.55); `field.cell_opening_plane` gives (12.75, 15.767, 59.55). Corner differences 0.016 to 0.017 in (0.065 to 0.079 in if the opening plane is taken at z_loc 0 instead). All under 0.1 in: NOT refuted. Official figure 9-9 values (53.5, 65.6, 30.6, 25.5 center to center) agree with field.py.
- Tag row: CAD sticker center + 0.25 in along the beam (sticker 5 in tall, holes on its bottom edge, tags 2.75 in above them, Figure 9-15) = (12.742, 13.104, 49.791); `field.hive_tag_corners` row center (12.75, 13.102, 49.79); 0.009 in. Offsets +-2.75, +-6.5 in match Figure 9-15. Id order along X (ids ascend toward -X) is consistent with my reading of the sticker frame but cannot be proven from the CAD (the sticker has no art): still VERIFY.
- **HIVE frame: contradicts the CAD by 29.7 in.** `evidence/refute/dod9_2/frame_cad.py` (`frame_cad.txt`): the official STEP `am-5854 Frame` is an A-frame (Figure 9-8 shows the same): two foot bars at x = +-24.73 spanning y +-19.47 on the floor, four legs rising to a 24 in top bar at |y| < 1.5 in, highest vertex 44.31 in. No CAD frame vertex exists above 44.31 in. field.py/field_constants.py model a rectangular box with top bars at (+-24.73, +-19.475, 63.95) (`FRAME_TOP_Z = PIVOT_HEIGHT + 20.0  # assumed`). The nearest real frame vertex to each modeled "top corner" is (+-13.7, +-0.4, 44.0), 29.7 in away. The width 49.46 and depth 38.95 are real (foot bars), the height 63.95 and the top bars at y = +-19.475 are not. These four points are kit tags 100-103, calibration click points 5-8, the "audience-side top bar" used for the in-frame roll check, the map's frame box, and the occlusion wireframe. calibration.md, camera_placement.md and field.py label them "VERIFY / CAD guess / assumed"; nothing acknowledges that the structure has a different shape.
- Perimeter wall: the CAD field walls are at |x|,|z| 71.65 (outside, panel links), glass 70.67 to 70.79, tiles to 70.58 (`wall_cad.py`), i.e. an inside face near 70.7 in, not 72. The manual says "approximately 144 in" and the setup guide says tiles are wider than the perimeter. Doc/placement constants (72 inside, +1.5 in thickness -> 73.5 outside) differ from the CAD outside face by about 1.85 in: real tape numbers would be about 6.35 in out and 6.65 in along (A) instead of 4.5 and 8.5. Calibration measures the real pose, so this only shifts tripod spots by 2 in, but the "tape" numbers are off by more than 0.1 in.

## 4. Followability, what an operator cannot do

Cannot do at all:
1. Tape kit tags on "the audience-side top bar / the frame's top corners" (calibration.md 3A, section 0 step 3 "height of the frame's top bars (model: 63.95 in)"): no such bar or corner exists. A person would measure ~44 in at the ridge and no bar at y = +-19.5. Following the document faithfully places tags somewhere else (or nowhere).
2. Click points 5-8 (calibration.md 3B; "frame top corner (-X,-Y)" etc.): not physical. Points 1-4 (CELL corners) are physical.
3. The in-frame roll check (camera_placement.md step 5) uses the audience-side top bar (points 5 and 6): not physical.
4. Step 7 / step 4 "all 8 calibration points must be visible": 4 of them do not exist.
5. The crosscheck "within 1 in of CAD" that the Claim names: the app has POST /api/calib/crosscheck (ui/app.js renders it; calibration.md section 5 step 4 wrongly says there is no button) but it triangulates the same clicked points that were used to solve (in-sample), and the opening center itself is not a clickable point. Nothing in the app checks the claim; only a developer simulation does.

Under-specified or inconsistent:
6. Aim point is a 3-D point in the air; the doc substitutes a floor cross at (13,37) or (12,32). It never says how to find field coordinates on the floor (field center is a tile-corner intersection; which axis is X). Mirror hazard handled once ("check red is on your left") - good.
7. Tripod feet are never placed. Lens plumb spot is 4.5 in from the outside face (6.35 in by the CAD walls). With three legs at 120 deg the nearest foot is at least half the foot radius toward the wall, so any tripod with feet more than 9 in (or 12.7 in by the CAD) from its axis (a normal low 60 in tripod at 20 in lens height) puts a foot on or over the wall. The doc says "draw the foot triangle around the plumb spot" and does not address this. Not verifiable offline without the real tripod; flagged as likely.
8. Tolerances: the doc gives +-3 deg yaw, +-2 deg pitch, +-1 deg roll but no position tolerance and no check that the lens is plumb over the cross.
9. PURCHASE_LIST.md step 3 still says "lens 36 in high" for both cameras and "6 in outside the wall" and quotes a 117 deg triangulation angle (PURCHASE_LIST.md "Third camera" note); docs now say 30 / 20 in and 105 deg. operator_guide.md section 3 and PURCHASE_LIST step 5 still tell the operator to "click the listed points" with the tag kit not mentioned.
10. Robot occlusion assumption: STATED (camera_placement.md rule 4, section 6 sensitivity row, section 7: box 18 x 18 x 24 in plus 3 in extension, 90 % free-ray hard rule; 9 in extension drops B to 86 %). Not a gap. Minor: field_constants.ROBOT_HEIGHT = 18 vs the placement box height 24 in; the occlusion wireframe uses the nonexistent frame box and (by default) both HIVEs audience-up.
11. cam0 / cam1 identity: stated (A = cam0, B = cam1, hand-wave test, direct USB ports). Not a gap.

## 5. Practicality

- UBeesize MT60 minimum height: not available offline. SHOPPING_LIST.md and PURCHASE_LIST.md only list the product link, "60 in", 1/4-20; neither gives a minimum height. camera_placement.md asserts "practical minimum of the UBeesize MT60 tripod 20 in" (and the code `HEIGHTS_IN` comment) without a source. Assumption: a 60 in aluminum tripod's lowest mount is around 17 to 24 in at the head; the lens sits 2 to 4 in above the tripod plate with the bracket and board, so a 20 in lens height needs a head at about 16 to 18 in. UNVERIFIED; B (lens 20 in) is the risky one. Lens 30 in for A is safe.
- Feet footprint at 20 in (item 7 above) is the more probable practical blocker.
- B at (65,78) is in the drive team's audience-wall corner (doc says to keep the team away), and cable routing 16 ft is documented.

## Summary of what refutes

1. The reference geometry for the printed kit and click points 5-8 is not on the real HIVE (CAD A-frame tops out at 44.3 in; modeled corners are 29.7 in from the nearest real frame vertex). The documented procedure cannot be carried out, and calibrated results are only as good as an unreal model.
2. Even in the unreal-but-idealized world the "under 2 px" gate fails for realistic tag mounting error (0.25 in: 19 to 23 of 30 pass; 1 in: 0 or 1 of 30) and for per-point click gating at 1.5 px.
3. The claim's "known point within 1 in" check is not performed anywhere in the app (crosscheck is in-sample).
4. Supporting gaps: stale PURCHASE_LIST / operator_guide, unplaceable tripod feet, unverified MT60 minimum, 2-tag HIVE-only solutions can flip with low reprojection.

What is NOT refuted: map/doc/recommend() consistency (byte identical regenerations, all numbers), CELL opening and tag-row geometry vs CAD (0.02 in), robot assumptions stated, idealized-world numerics (kit 0.1 in, 1 px).

## Suggested fixes
Replace frame-top-corner targets with physically real CAD points (e.g. the A-frame top corners at (+-13.7, +-0.4, 44) or the two up CELLs' opening corners: the 8 CELL corners of red-audience-up and blue-far-up gave 0.26 in / 1.6 px / flight RMS 0.5 in in the click simulation, all in frame), regenerate kit positions from the CAD frame, add a test that compares frame coordinates against the STEP extraction, stop treating them as "VERIFY" numbers, state the tripod-foot rule and tape numbers from the CAD wall (outside face about 71.65), fix PURCHASE_LIST step 3, require 3 tags before saving a tag solve, and give an independent (not in-sample) 1 in check.

## Files
`evidence/refute/dod9_2/`: `regen/` (4 regenerated maps), `check_doc.py`, `check_pct.py/.txt`, `check_alt.py`, `sim.py`, `sim_usb.txt/json`, `sim_gopro.txt/json`, `agg.py/.txt`, `nominal_detect.py`, `nominal_detect2.py` (+ two B_*.png frames), `cad_vs_field.py/.txt`, `frame_cad.py/.txt`, `wall_cad.py`, `real_top_pct.py/.txt`, `step_summary.txt`, `inimg.py`, `patch1.py`.

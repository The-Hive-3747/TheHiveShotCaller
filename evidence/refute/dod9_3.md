# Refutation report dod9_3 (DoD 9, round 3)

Claim: "A camera placement map and placement instructions exist in the project folder, and a fresh setup following them yields calibration within the M1 accuracy target" (reprojection under 2 px per camera; the up-CELL opening center triangulates within 1 in of its CAD value).

**VERDICT: REFUTED.** The map, the document and every number in them are consistent with `placement.recommend()` (byte-identical regeneration), and the frame is now the right kind of structure (A-frame; foot bars, legs, crossbar, pivot cradles all match the CAD to 0.01 in). But the **logo panel is modeled as a vertical plate at y = 4.28, and the real CAD panel is a flat plate leaning 24 deg with the legs**. Kit tags 100 and 101 are defined on that nonexistent vertical plane. A tag taped on the real panel as the docs say is 1.4 in (center) and 24 deg (normal) away from the model; the kit solve then gives 5.2 to 6.5 px reprojection and a 1.8 in opening-center error in 0 of 30 runs under either gate, even with perfect taping everywhere else. Secondary: the drive team premise is contradicted by the official field setup guide, and the in-app Cross-check cannot be the out-of-sample 1 in test the claim names when only B reads the CELL tags.

Everything is under `evidence/refute/dod9_3/` (read-only on source; no installs, no servers, no git). Run with `PYTHONPATH=. .venv\Scripts\python.exe <script>` from the project root. `tests/test_placement.py tests/test_tagkit.py tests/test_calib.py` pass when I re-ran them (`-p no:cacheprovider`): the tests agree with the model, which is exactly the problem (they test self-consistency, not the CAD panel).

## 1. Frame vs CAD vs Figure 9-8

Checked `field_constants` / `field._frame_segments` / `frame_reference_points` against `evidence/m1_field/step_extract.md` and an independent re-extraction from the STEP (`panel_cad.py`).

| Feature | field.py | CAD | verdict |
|---|---|---|---|
| Foot bar outer / inner x, half length y, height | 24.73 / 22.75 / 19.47 / 2.15 | 24.729 / 22.75 / 19.472 / 2.148 | match |
| Footprint 49.46 x 38.95 | yes | Fig 9-8: 49.46 x 38.95 | match |
| Leg apex end (12.60, 0.52, 41.05), foot end (23.81, 18.56, 0.53) | yes | same | match |
| Crossbar x +-12.0, z 41.45, 1 x 1 in | yes | same | match |
| Pivot cradle (12.0, 44.27) / (11.15, 41.57) | yes | same | match |
| Foot bar end cap (am-5879) top z 2.13, y 19.48 | not modeled, tag leans on 2.15 | present | consistent to 0.02 in |
| **Logo panel (am-5877 + sticker am-5883)** | vertical rectangle at y = +-4.28 (`FRAME_LOGO_PANEL y_outer`), z 34.07..40.02, x +-15.07 | **plate leaning 24.0 deg**: top edge at y = 1.55 (back) / 1.66 (sticker face), z 40.02; bottom edge y = 4.18 / 4.29, z 34.07 / 34.12; slant height 6.46 in; unit normal (0, 0.914, 0.407), i.e. facing the audience AND up; outline a trapezoid (top flat edge only x +-13.21, bottom +-14.57, widest +-15.06 at z 34.7) | **WRONG** |

Evidence: the 24 sticker vertices (`panel_vs_tag.txt`): (+-13.2, 1.657, 40.02) top, (+-14.6, 4.283, 34.12) bottom; ACM thickness 0.118 in. 24.0 deg equals the leg lean atan(18.04/40.52). Figure 9-8 shows the panel leaning on the legs. The "1.55 to 4.28 in" y range in the docs is the tilt, not a thickness.

Consequences for the kit (tag 100 / 101, `tagkit._pose`: vertical, normal (0,1,0), center (+-12, 4.28, 37.02), top edge z 40.02):
- A tag taped flat on the real panel, top edge flush with the panel top, centered x = +-12 (what calibration.md says) has center (+-12, 2.88, 37.28): **1.42 in from the model center (dy -1.39, dz +0.26), top corners 2.61 in off, bottom corners 0.55 in off, normal 24.0 deg off**. Against the stated tolerance (0.25 in / 0.5 deg) that is 5.6x and 48x.
- The model tag floats 2.39 in in front of the real surface at its top edge. calibration.md asks for both "the tag is vertical, top edge flush with the panel's top edge" and "its face is the panel face": impossible on the real panel without an unspecified 2.4 in standoff. Measuring "how far the audience face is in front of the center line (model 4.3 in)" (section 0 step 3) would return 1.6 at the top and 4.3 at the bottom; the doc's "more than 0.5 in, tell the developer" rule fires but the operator cannot resolve it.
- The panel is not wide enough at the top for a tag centered at x = 12: at z 40 the panel half-width is 13.24, the tag outer edge is 15.0, so the two upper outer corners overhang the panel by 1.76 in (1.1 at z 39, 0.6 at z 37, 0 at z 35). The tag still sticks on foam core, but its corner hangs in the air (`panel_vs_tag.txt`).
- The "6 in tag on a 5.95 in tall panel, 0.05 in overhang" statement: wrong reason. 5.95 is the vertical extent; the plate is 6.46 in tall along its face, so the 6 in tag fits with 0.46 in to spare. The 0.05 in overhang is physically meaningless.
- Real tag angles from the recommended cameras (tilted normal faces up, cameras are at 20 in): 100 in A 48.6 deg (model 37.5), 101 in A 54.9 (46.5), 100 in B 54.9, 101 in B 48.6. Tags 101(A) and 100(B) land at the 55 deg readability limit the doc uses, and base tag 103 in A is already 54.0 deg. They still decoded in every synthetic run, so this is a margin remark, not a failure.
- The same vertical plate is drawn in the map and used by the occlusion wireframe (`field._frame_segments`), a small error.

Tags 102 / 103 (base): real. Foot bar end top edge at (x 22.75..24.73, y 19.47, z 2.15) with an end cap of the same height; the tag plane y = 20.25 - 0.364 z touches y = 19.47 at z = 2.15 (exact). The leg centerline foot end is at (23.81, 18.56, 0.53); tag-to-leg clearance computed 0.7 to 1.9 in over the tag height, so the tag fits in front of the leg. Reachable with a tape (tile level, outside the frame footprint). Practicality caveat, stated in the docs only as "demanding": a 6 in card leaning on a 2 in wide bar end must be placed to 0.25 in and 0.5 deg; one 0.5 deg error is 0.05 in at the top, fine, but a freestanding card on a wedge in a gym is the weak link of the whole kit.

CELL geometry (opening center (12.75, 15.77, 59.55), tag row (12.75, 13.10, 49.79)): unchanged from round 2, matches CAD to 0.02 in (not re-attacked).

## 2. Map and document vs `recommend()`

- `placement.write_map('usb'|'gopro', ...)` into `regen/`: SHA256 (first 16 hex) identical for all four files: `camera_placement.svg 859ef4ba...`, `.png 660a7eb9...`, `_gopro.svg 4a26e5ea...`, `_gopro.png f65eb17a...`. NOT refuted.
- `recommend('usb'|'gopro')` (`doc_nums.txt`): A (-72, 85.5, 20), B (72, 85.5, 20), C (13, 85.5, 58); out from OUTSIDE face 12.00 in (tripod spot 12 in outside the wall), along from outer edge 1.50 (C 60.50); yaw/pitch A GoPro 327.2 / 8.6 (doc 327 / +9), A Arducam 329.0 / 10.4 (329 / +10), B GoPro 215.2 / 11.0, B Arducam 218.4 / 12.5 (218 / +13); aim points (11,32,35), (12,35,38), (9,41,35), (12,38,37); tag reader B (50.8 deg, 22.1 px Arducam / 26.5 GoPro), A 57.5 deg (15.8 / 18.4 px); kit readable A 100-103 both options, B 100-103 (Arducam), 100/101/102 (GoPro); triangulation 96.7 / 97.1; both-seen 100 % / 96.5 %; robot-free A/B 100 / 98 %; ball diameters 20.5-45.1 mean 24.5 (A Arducam) etc. All match the doc to the printed precision. NOT refuted.
- The doc statement that both cameras end up on the audience wall because "no other pair meets rules 1-5" holds in the code (`both_on_audience_wall: True`); its stated reason (drive team at the audience wall) is false, see section 5.
- Stale comments in `placement.py` (lines near 70-80: "4 in tags on the frame top corners", "2 is the requirement" vs `KIT_MIN_TAGS = 3`): cosmetic.

## 3. Operator simulation (30 seeds, 1920x1080, `sim3.py`, outputs `sim3_usb|gopro.txt/json`)

Method: predecessor's harness (`dod9_2/sim.py` helpers). True camera at the documented spot with placement error uniform +-1 in x/y, +-0.5 in lens, +-2 deg yaw and pitch, +-1 deg roll. Kit tags 100-103 plus the four up-CELL tags 34-37 rendered (2 gray-level noise, 3x3 blur), decoded with `calib.detect_apriltags`, 0.5 px Gaussian noise on each corner, `solve_extrinsics_from_points(use_ransac=False)` (same path as `solve_extrinsics_from_tags`) against the MODEL tag corners. Each kit tag then displaced 0.25 in (random direction) and tilted 0.5 deg (random axis), the documented tolerance. Opening center projected through the true cameras (0.5 px) and triangulated with the estimated poses. Out-of-sample check = HIVE tag corners decoded in both cameras, triangulated, max corner error vs CAD. Click method: 8 CELL corners, 1.5 px noise. Two worlds: **model** (tags exactly where `tagkit` says) and **real** (100/101 flat on the real tilted panel as documented, 102/103 as modeled).

Arducam ("usb"; GoPro within 0.1 px and 0.1 in in the model world):

| World / method | reproj px cam0 / cam1 (median) | runs both cameras < 2 px | opening-center error in, median / max | runs < 1 in | runs passing BOTH gates | out-of-sample HIVE-tag check max in (median) |
|---|---|---|---|---|---|---|
| model, tags exact, kit | 0.89 / 0.92 | 30/30 | 0.10 / 0.19 | 30/30 | 30/30 | 0.22 |
| **model, 0.25 in / 0.5 deg, kit** | 1.26 / 1.21 | **29/30** | 0.27 / 0.44 | 30/30 | **29/30** | 0.40 (30/30 under 1 in) |
| **real panel, tags exact, kit** | **5.50 / 5.25** | **0/30** | **1.85 / 1.94** | **0/30** | **0/30** | **1.68 (0/30 under 1 in)** |
| **real panel, 0.25 in / 0.5 deg, kit** | 5.54 / 5.41 | **0/30** | 1.82 / 2.12 | **0/30** | **0/30** | 1.70 (0/30) |
| click 8 CELL corners, 1.5 px (same in both worlds) | 1.59 / 1.60 (0.25 in case 1.58 / 1.84) | 18/30 | 0.26 / 0.59 | 30/30 | 18/30 | not applicable |

GoPro: model 0.25 in 29/30 both gates, real panel 0/30 (reproj 6.3 / 6.2 px, opening center 1.84 in), click 18/30 (19/30 in the second case). Camera position error in the real world: 2.8 in median (5.0 in max), rotation 1.9 deg.

Read-out:
- With the documented procedure on the real frame, the kit calibration **never** meets the 2 px target and **never** meets the 1 in opening-center target (0/30 per gate, both options), even before any human error. In the app the operator would see 5 to 6 px, be told to "re-measure the tags", find every tag exactly where the doc says, and have no way to fix it. calibration.md step 5 only tells them to re-measure.
- The failure is detectable (in-sample check vs the model: 1.2 to 1.4 in, red, 0/30 under 1 in; out-of-sample 1.7 in), so the app does not silently pass. It is a refutation of the claim ("a fresh setup following them yields calibration within the target") not a silent bug.
- In the model world the claim holds at the documented tolerance (29/30). This is the best case the docs can reach; the 1/30 miss is B at 2.30 px.
- The click fallback is physical (corners of the two up CELLs exist) and keeps the opening center under 1 in in 30/30, but "reprojection under 2 px per camera" holds in only 23-26/30 per camera, 18/30 both, at 1.5 px click noise. calibration.md 3B step 5 requires **every point** under 2 px: 0/30 both cameras (per camera 9/60 Arducam, 10/60 GoPro), so by its own acceptance rule the operator is told to redo almost always. The click path therefore does not reliably meet the target either.
- Caveats on the simulation: exact intrinsics, no lens distortion, no video compression, perfect synthetic renders. cam A decodes the CELL sticker tags in my render (3.83 of 4 per camera) although the docs say it is too oblique; real optics and video will do worse, so the out-of-sample check may not be available at all (see section 5, Cross-check). Dependence of the 5 px result on these assumptions is small: it is a geometric offset of 1.4 in and 24 deg, far above the noise.

## 4. Followability: what an operator cannot do with a tape and the docs

Cannot do:
1. Mount tags 100 / 101 "vertical, top edge flush, face at y = 4.28" on a panel that leans 24 deg (section 1). Following the words places the tag flat on the panel at a different pose.
2. Resolve the contradiction when the measurement in calibration.md section 0 step 3 differs from the model (the panel face distance has no single value).
3. Place a freestanding 6 in card leaning 20 deg against a 2 in bar end to 0.25 in / 0.5 deg: needs a tilt gauge (the phone level app helps) and a rigid stand; docs say "card easel or foam wedge" without dimensions.
4. Measure the aim crosses "at (+11, +32)" on the field floor: no instruction on locating the field center and the axis direction beyond "middle between opposite walls" and "+X is on your left at the audience wall". The 24 in tile grid is not used as a ruler (e.g. 12 in off a tile seam), which would make this trivial.
5. Verify the UBeesize MT60 minimum lens height of 20 in or the leg radius (both flagged VERIFY). The tripod feet rule is concrete (one leg straight away from the wall, the two others 60 deg either side toward it, lens spot 12 in from the OUTSIDE face keeps feet 2 in clear for a 20 in leg radius, general rule R/2 + 2 in, tape the three foot spots first) and I could follow it with a tape. Gap: if R/2 + 2 exceeds 12 in the doc says the lens must go further out but does not say that all numbers in the aim table then need re-derivation; at R = 20 in lens height 20 in a 60 in tripod is an assumed, unverified stance.
6. The setting is named `field_size` in calibration.md and camera_placement.md; the app calls it `field_size_in` (Settings, "Field size (in)").

Stated (not gaps): robot occlusion model (box 18 x 18 x 24 in + 3 in, 90 % rule, 12 in extension sensitivity, "occlusion by people or the audience barrier is not modeled"), field size (144 in assumed, measure yours, tape numbers are wall-relative), wall thickness 1.5 in VERIFY, tags 102/103 need an empty field (a robot hides them), cam0 / cam1 identity test. Unmodeled and not stated: the four Flower assemblies on the perimeter (CAD: 5.9 x 5.0 in footprint, 22.65 in tall; one at x -26.7..-20.1, y 65.6..71.8 on the audience wall, one on each other wall). A box test (`flower_occ.py`) puts 4.1 % of the ball sample rays from camera A through the audience-wall flower box (0 % from B), so not decisive, but the flowers are skeletal rings and strips plus pollen balls, and the doc says nothing about them.

## 5. Drive team and Cross-check

**Drive team.** The docs claim the cameras are on the audience wall because it is where "the drive team stands" and that "the drive team stands between them". The official Event Field Setup Guide section 8.5 (page 15 figure; `docs/official/event_field_setup_guide.pdf`, extracted images in `fsg/`) puts the **Red Alliance Area on the left and the Blue Alliance Area on the right of the field**, each 54 in deep and about 97 in wide, centered on a side wall (tape aligned with Tile Seams 1 and 5, i.e. y roughly -48..+48). The cameras at (+-72, 85.5) are about 37 in beyond the end of each alliance area along the wall, at the audience-side corners. So the drive team is not at the audience wall; the premise behind rule 6 and the `_corner_factor` (placement.py) is wrong, and "between them" has no meaning for an audience wall that is not an alliance station. The effect on the recommendation is benign (corners are clear of the alliance areas, the camera rays do not pass the alliance area), but what would matter is that a side-wall camera sits inside an alliance area, which the docs do not say. Open: where the audience barrier and spectators stand relative to a tripod 12 in outside the audience wall (not in any document in the repo); the docs' only mitigation is "keep the drive team's station away from the corner tripods and keep people out of the line", which is untestable and based on the wrong location.

**Cross-check.** `/api/calib/crosscheck` (app.py) is out-of-sample only if a tag not used by either solve is decoded in both cameras. After a kit solve the unused tags are the HIVE tags 34-37; the docs say only B reads them (A sees the sticker at 57 deg, 16-18 px). If A cannot decode them, `_held_out_points` returns nothing and the function falls back to the in-sample kit-tag corners with a warning. My in-sample figure for the real world is 1.2 to 1.4 in (red), so this fallback does flag the tilt, but its green case does not test the up-CELL opening center the claim names. Nothing in the app checks "opening center within 1 in of CAD".

## Weaknesses (not each refuting)

1. Panel plane error (above): the refuting item.
2. The CELL tags that give the independent check are decoded by B only (docs), so the claimed independent verification may not be available at all with the recommended placement.
3. Tolerance chain is demanding: 0.25 in / 0.5 deg gives 29/30 in the ideal model; any systematic error larger than that fails (0.5 in / 1 deg: 9/20 per the dod9_fixes study).
4. Click fallback only 18/30 at 1.5 px for RMS < 2 px; "every point < 2 px" rule is almost never met.
5. Stale comments in `placement.py`; field wall inside size 144 vs CAD 141.35 handled by the "measure" instruction (OK).
6. Not re-run: real-camera decode of 6 in tags at 22-33 px and 55 deg through RTMP / mp4; the 22 px / 51 deg CELL tag read in B is geometry-only (docs flag it VERIFY).

## Suggested fixes
- Put the tag on the real plane: panel face through (y 1.66, z 40.02) and (y 4.29, z 34.12), normal (0, 0.914, 0.407), tag center at 3 in along the slant, shifted inward (center x about +-10.5 so the upper outer corner stays on the trapezoid), and mount them flat on the panel; update `tagkit._pose`, the doc text (drop "vertical" and "4.3 in in front"), `field.FRAME_LOGO_PANEL` and the wireframe, and add a test that compares the panel plane with the STEP extraction (the existing tests only check the model against itself).
- Re-run readability (tag angles with the tilt, 101 in A and 100 in B at 54.9 deg) and `recommend()` after the change.
- Replace the drive-team rationale with the alliance-area fact and state where a spectator barrier / tripod must not stand.
- Say in the click method how to verify 2 px per camera RMS rather than every point, or reduce click noise (zoom).

## Files
`evidence/refute/dod9_3/`: `panel_cad.py`, `panel_vs_tag.py/.txt`, `real_angles.py/.txt`, `rec.py/.txt`, `doc_nums.py/.txt`, `regen/` (4 regenerated maps), `sim3.py`, `sim3_usb.txt/json`, `sim3_gopro.txt/json`, `sim3_*_stdout.txt`, `flower_occ.py/.txt`, `fsg/` (extracted setup-guide figures).

# Refutation report dod9_4 (DoD 9, round 4)

Claim: "A camera placement map and placement instructions exist in the project folder, and a fresh setup following them yields calibration within the M1 accuracy target" (reprojection under 2 px per camera; the up-CELL opening center triangulates within 1 in of its CAD value).

**VERDICT: REFUTED (narrowly, on a physical-visibility defect), everything else NOT REFUTED.**

The round-3 defect (tags on a vertical plate) is fixed: the kit tags are on the real panel plane, the map and doc are byte-identical to `recommend()`, and the kit solve now passes both gates in simulation. What remains is a new, different defect that none of the earlier rounds or the tests model: **in the documented HIVE state (red audience CELL up, blue far CELL up) the blue audience CELL is DOWN and its solid body stands between both cameras and tag 100** (and half of tag 101 from camera A). The doc says camera A reads kit tags 100, 101, 103 and B reads 100 to 103; in the CAD geometry A can decode only tag 103, so the documented primary procedure (kit Auto-calibrate) cannot calibrate camera A at all. A fallback (click method for A) exists in the doc and does reach the target with retries, which is why this is "narrowly". Details in section 3b.

All work is under `evidence/refute/dod9_4/` (source read-only; no installs, no servers, no git; single-process sims). Run as `PYTHONPATH=. .venv\Scripts\python.exe <script>` from the project root. `tests/test_placement.py tests/test_tagkit.py tests/test_calib.py` pass (all green, 18 s, `-p no:cacheprovider`); they check the model against itself and do not model the CELL bodies.

## 1. Logo panel and tags vs the STEP numbers: NOT REFUTED

`panel_check.py`:
- `field.logo_panel_face("audience")` corners: bottom (+-14.58, 4.292, 34.125), top (+-13.22, 1.666, 40.024): max abs difference to the step_extract.md numbers **0.000 in**; normal (0, 0.9136, 0.4067) vs (0, 0.9135, 0.4067): 5e-5; planarity 3e-4 in. The raw vertex list (`evidence/m1_field/step_panel_out.txt`) agrees (x 13.212/13.226 at the top, 14.587 at the bottom, with the chamfers at x 13.7 / tabs at 15.07 not used).
- Tags 100 and 101 (`tagkit.KIT_TAGS`): every corner within 0.0003 in of the plane; top edge on the panel's top edge (s = 6.457 of 6.457); outer corners at x = +-13.000 (0.220 in inside the top corner 13.22); lower corners 1.48 in inside the trapezoid width at their height; 0.457 in above the panel's bottom edge. Inside the trapezoid, on the plane. OK.
- Tags 102 and 103: bottom edge on the tile at y = 20.2525, top at (y 18.2, z 5.638), normal (0, -0.94, -0.342) toward the viewer after the corner-order flip (= (0, cos20, sin20) face); the face plane crosses z = 2.15 at **y = 19.470**, exactly the foot bar end top edge (19.47, 2.15 from the CAD). Touches a real surface (the foot bar end), x extent -24.73..-18.73 (outer edge flush with the foot bar outer face; only the outer 1.98 in of the 6 in width touches the bar, the rest overhangs open floor).
- Panel and base tags are on real surfaces. This item does not refute.

## 2. Map and document vs `recommend()`: NOT REFUTED (with minor remarks)

- `regen.py`: `write_map('usb'|'gopro')` regenerated to `evidence/refute/dod9_4/regen/`: **all four files byte-identical to docs/** (sha256 prefix: `camera_placement.svg c5079f81`, `.png 7943005f`, `_gopro.svg 8947bd41`, `_gopro.png 3a7c68cd`).
- `doc_nums.py` / `occl.py` / `doc_pct.py` (outputs `doc_nums.txt`, `occl.txt`, `doc_pct.txt`), everything matches the document:
  - Positions: A (-49, 85.5, lens 36), B (+72, 85.5, lens 20), C (+13, 85.5, 58); 12.00 in out from the outside face; 24.5 / 1.5 / 60.5 in along from the corner's outer edge. Yaw/pitch: Arducam A 319.9 / 0.7 (doc 320 / +1), B 218.4 / 12.5 (218 / +13); GoPro A 318.9 / 0.0 (319 / +0), B 216.3 / 11.8 (216 / +12). Aim points (11,35,37) (12,38,37) (10,34,36) (10,40,36) as in the doc.
  - Tag reader: B at 50.8 deg (doc 51), A 60.0 deg; B CELL-tag edges 22.1 px (Arducam) / 26.2 px (GoPro); kit tags readable A 100/101/103 (both), B 100-103 (Arducam) / 100, 101, 102 (GoPro) (geometry only, see 3b).
  - Triangulation 91.8 / 92.4 deg (92); arcs seen by both 99.7 % (Arducam, doc 100 %) / 93.4 % (GoPro, 93 %); rays blocked by frame or FLOWER 0.63 % (Arducam, doc 0.6) / 0.32 % (GoPro, 0.3); robot-free A/B 100 % / 98 %; ball diameters (26.5/32.5/65.4, 24.4/31.1/75.9; 31.2/37.9/74.0, 28.8/36.5/88.0; C 43.6-85.8 / 51-98.2) all as stated.
  - FLOWER numbers: old A spot (-72, 85.5, 20): **4.11 %** of ball rays blocked by the cylinder model (doc 4.1; an independent CAD footprint box test gives 3.8 %); new A (-49, 85.5, 36): **0.95 %** (doc 0.9; box test 0.95 %); B **0.32 %** (doc 0.3; box 0 %). Flower centers (+-23.4, -+68.1), (+-68.1, +-23.4), radius 3.86, top 22.65 match step_extract.md; the one on the audience wall is at x = -23.4.
  - Picture percentages (CELL opening center A 57/26 GoPro, 57/30 Arducam, B 38/29, 41/34; tag rows; the 16 kit-tag percents for GoPro; roll line slope A about 1 deg, B 16.8 px per 100 px = 9.5 deg) reproduce exactly. Aim slack: GoPro B fails at 3.5 deg and passes at 3.0 (doc 3), Arducam B fails at 6.0, passes at 5.5 (doc 5.5). The "slack" is a pure image-bounds computation (again no occlusion).
- Remarks: the tagkit docstring still says "tilt to 1 deg" where calibration.md and camera_placement.md say 0.5 deg; calibration.md section 3A step 8 says "with `hive_tags` on, Auto-calibrate uses them together with the kit" while `auto_all` (the button) solves from the kit first and keeps the HIVE tags out (source "kit"); the doc's 12 in extension numbers (93 %) were not re-run (unchanged since round 3).

## 3. Operator simulation (30 seeds, single process): kit and click methods

Method: `sim4.py` (harness of dod9_2/dod9_3: true camera at the documented spot with placement error uniform +-1 in x/y, +-0.5 in lens, +-2 deg yaw/pitch, +-1 deg roll; tags 100-103 and HIVE tags 34-37 rendered 1920x1080 (2 gray-level noise, 3x3 blur), decoded with `calib.detect_apriltags`, 0.5 px corner noise, `solve_extrinsics_from_points` against the MODEL kit corners, i.e. the same path as `solve_extrinsics_from_tags`). Mounting error: each kit tag displaced 0.25 in (random direction) and tilted 0.5 deg (random axis). Opening center = triangulated up-CELL opening center vs CAD (0.5 px noise kit, 1.5 px click). Outputs `sim4_usb.txt/json`, `sim4_gopro.txt/json`.

### 3a. As the model has it (no CELL bodies): NOT REFUTED for the kit path

| Case | Option | reproj < 2 px both cams | opening center < 1 in | both gates | camera pos err median / max (cam0, cam1) | out-of-sample HIVE-tag check (max corner err) | in-sample kit check |
|---|---|---|---|---|---|---|---|
| exact tags | Arducam | 30/30 | 30/30 (med 0.11, max 0.22 in) | 30/30 | 0.45 / 1.1, 0.21 / 0.48 in | 0.21 median, 0.37 max | 0.16 / 0.23 |
| exact tags | GoPro | 30/30 | 30/30 (0.12 / 0.27) | 30/30 | 0.57 / 1.0, 0.25 / 1.3 | 0.21 / 0.33 | 0.11 / 0.18 |
| **0.25 in, 0.5 deg** | Arducam | **30/30** (reproj median 1.14 / 1.24, max 1.88 / 1.82) | **30/30** (med 0.33, max 0.59) | **30/30** | 1.6 / 6.4, 1.0 / 2.7 | 0.41 median, 0.87 max (30/30 under 1 in) | 0.24 / 0.37 |
| **0.25 in, 0.5 deg** | GoPro | **30/30** (1.05 / 1.03, max 1.84 / 1.87) | **30/30** (0.33 / 0.74) | **30/30** | 2.2 / 5.2, 1.3 / 3.7 | 0.43 / 0.76 (30/30) | 0.17 / 0.28 |
| 0.25 in, 0.5 deg **plus base tags 102/103 raised 0.5 in along the slope** (see 4) | Arducam | 29/30 | 27/30 (max 1.23 in) | 27/30 | 2.5 / 9.1, 2.1 / 4.2 | 0.67 median, 1.40 max (28/30) | 0.24 / 0.36 |
| same | GoPro | 27/30 | 27/30 (max 1.22) | 27/30 | 2.7 / 7.4, 2.1 / 4.8 | 0.73 / 1.19 (27/30) | 0.18 / 0.33 |

So at the documented tolerance the kit path meets both gates 30/30 in the idealised (all tags visible) world, better than the 29/30 the docs report (different seeds).

Caveats on this table, all of which favour the claim: (i) in the synthetic render camera A decodes all four HIVE tags (60 deg, 21 px edges) and all kit tags; the doc itself says A cannot decode the CELL tags, so in reality only B reads them and the "out-of-sample" column is not available for A; the doc states this honestly in calibration.md section 5; (ii) no CELL body occludes anything in the renderer (section 3b); (iii) exact intrinsics, no distortion.

### 3c. Click method (8 CELL corners, 1.5 px) against the NEW gate (RMSE < 2 px and no point > 3 px)

`sim4.py` (30 seeds) and `click_many.py` (300 seeds, no rendering; outputs `click_many.txt`):

| Option | per camera: gate passed | both cameras pass on the first try | RMSE < 2 px only (per camera) | opening-center error < 1 in |
|---|---|---|---|---|
| Arducam, 30 seeds x 3 cases (pooled) | 120/180 = 67 % | 36/90 = 40 % | 145/180 = 81 % | 90/90 (median 0.25, max 0.60) |
| GoPro, 30 seeds x 3 cases (pooled) | 115/180 = 64 % | 34/90 = 38 % | 144/180 = 80 % | 90/90 (median 0.20, max 0.42) |
| Arducam, 300 seeds | cam0 67 %, cam1 71 % | **48 %** | 78 % / 84 % | 300/300 (max 0.69) |
| GoPro, 300 seeds | cam0 67 %, cam1 71 % | **48 %** | 79 % / 84 % | 300/300 (max 0.55) |
| 1.0 px noise (300 seeds) | 99 % / 99 % | 98 % | 100 % | 300/300 |

- The doc's table claims 76 % (RMSE under 2 and every point under 3) at 1.5 px per camera; I get 64-71 %. Slightly optimistic, not material. Per camera it is passed about two times in three; the pair on the first try about half of the time; the operator redoes the click set until it passes. The gate is a pure self-consistency gate (it measures click noise, not pose error), but the pose it lets through is good: the opening center is within 1 in in every run (300/300), so the click path meets the target conditional on the operator's gate, with retries. NOT REFUTED as a fallback.

### 3b. REFUTING finding: the down CELL hides kit tag 100 (and half of 101) from both cameras

The documented HIVE state (calibration.md section "Field axes", camera_placement.md step 1) is red audience CELL up, **blue far CELL up, therefore the blue audience CELL is down**. The CAD (raw STEP extraction `evidence/m1_field/step_extract_out.txt`, "Blue Cell (Audience)", CAD default state): ribs span field x -23.3..-2.3, y 6.7..25.0, **z 30.65..50.49**; bottom skin origin (y 7.62, z 37.86) tilting down toward the audience to about (y 17.8, z 32.0). The project's own CELL model (`field.point_inside_cell`, CELL_EXTENT_Y 12.04, same one used for the ball/opening geometry, agrees with the CAD within 1.5 in) gives the box x -22.8..-2.8, y 7.5..24.9, z 32.0..50.2. The panel and tag 100 are at x -13..-7, y 1.7..4.3, z 34.5..40.0: directly behind that cup as seen from the audience wall, and the cup is solid on the floor and the back (back skin at y about 7.4 to 14.4).

`tag_los.py` (49 sample points per tag, segment from the camera to the point against the four CELL boxes; `tag_los.txt`):

| Camera | tag 100 hidden | tag 101 hidden | tag 102 | tag 103 |
|---|---|---|---|---|
| A (-49, 85.5, 36) | **49/49 (fully hidden)** | **23/49** | 0 (but outside the picture) | 0 |
| B (+72, 85.5, 20) | **14/49** | 0 | 0 | 0 |

Same for both options. By hand: from A the ray to tag 100 is at z about 36 to 37 over y 7..25, inside the CELL's z range, and meets the CELL floor at y about 9 to 13; from B (rising 12 deg) it meets the CELL floor at y about 12.9.

Consequences (all checked, not asserted):
- **Camera A can decode only tag 103** (100 hidden, 101 half hidden, 102 outside the picture): `sim_occluded.py`, scene limited to the visible tags: **A kit solve fails 30/30 ("only tags [103]", min_tags is 2)**, both options. In the app, Auto-calibrate on `cam0` returns 422, `auto_all` then tries the HIVE tags, which A cannot read (60 deg), so `cam0` cannot be calibrated by the documented primary path. B (101, 102, 103) is fine (30/30 under 2 px).
- The documented claims "A reads kit tags 100, 101, 103", "all four kit tags inside the picture in B", the percent-of-picture table for tags 100/101 in A, and rule 5 of the placement search ("at least 3 of the 4 kit tags readable in both cameras") rest on `placement.kit_view`, which tests only angle, size, image bounds and sticker overlap, never the CELL bodies. The recommended placement was therefore optimised under a false visibility assumption (a placement or tag position that does see 3 tags may exist).
- The fallback in calibration.md (3A step 6: "If a camera cannot see 2 tags, use the click method for that camera") works: mixed route (A: 8 clicks, B: kit 101/102/103, 0.25 in / 0.5 deg): A passes the new gate first time in 24/30 (Arducam) / 22/30 (GoPro), opening-center error median 0.25 / 0.21 in, max 0.39 / 0.42, **30/30 under 1 in**; whole route passes every gate on the first try in 24/30 and 22/30 (retries needed otherwise).
- The Cross-check then loses its independence: after a mixed route (A clicks, B kit) there is no common clicked name between the two cameras ("422 no reference point was clicked in both cameras"), and no kit tag is unused by both; only the click-both route gives a held-out check (tag 103 only, since 100 and 101 are hidden from A).
- The click method also has hidden points: `click_los.py` finds point 7 (blue far low-right corner) in A's line through the blue audience CELL body, and points 5 and 6 (blue far high corners) in B's line through the red audience (up) CELL body (the corner rims of the far CELL are seen through the other cups). The doc lists them as visible at given picture percentages; only image bounds were checked (the same missing occlusion model).
- Remedy (not applied): model CELL bodies as occluders in `kit_view` and the point visibility check, then re-run `recommend()`; or specify a state in which the blue audience CELL is up as well (with HiveState("blue","audience") `tag_los_bothup.py` gives 0/49 hidden for every tag in both cameras, but click points 5-8 then have to be redefined on the blue audience up-CELL opening). Either needs the doc and the tests updated.

I did not verify opacity of the real skins (the CAD has them as solid parts and the ribs are 2 in thick); if the real cup were see-through the finding weakens, but nothing in the repository supports that and the documents assume nothing either way.

## 4. Followability and physical plausibility

- **Base tag stand:** yes, described, if briefly. calibration.md section 0 step 4b: "Tags 102 and 103 need a small stand: a card easel, or a wedge of foam core that holds the card 20 deg back from vertical"; section 3A table: bottom edge on the tile at 20.25 in (0.8 in beyond the end of the foot bar), outer edge flush with the foot bar outer face, leans back 20 deg, rests against the top edge of the foot bar end (2.15 in high), top edge 2.05 in nearer the frame and 5.6 in above the tile. No wedge dimensions given (a 20 deg wedge under a 6 in card is about 2.2 in at the back edge, derivable). Statics (my estimate, not run): a card leaning at 20 deg on the bar end carries about 0.45 of its weight on the bar corner, so the floor friction needed is about 0.5: marginal for a bare card on a tile, fine with a wedge or easel. The bar contact is only the outer 1.98 in of the 6 in width, so the inboard 4 in overhangs open floor; the phone level check on a card edge is the only tilt tool the doc offers. Followable with a wedge, tight (0.25 in, 0.5 deg) for a loose card.
- **Ambiguity worth an error budget:** "bottom edge on the tile" refers to the black square, but the same doc tells the operator to glue the tag on card "the size of the tag plus its white border" (0.5 in or more) and cut leaving the border, so the card stands on its border and the black square's bottom edge is about 0.5 in up the slope (0.47 in higher, 0.17 in toward the frame). Simulated: 27/30 pass both gates (both options) instead of 30/30; opening center up to 1.23 in. A one-line fix ("trim the border at the bottom or measure to the black square"). Likewise for 100/101 the white border hangs 0.5 in over the panel's top edge and 0.28 in over its top corner; harmless for a rigid card.
- **Tags 100/101 on the panel:** concrete (flat on the panel, top edge flush, x = -13..-7 and +7..+13, 0.2 in inside the corner), no stand needed; but see 3b: they are hidden by the blue down CELL, which the doc never mentions.
- **FLOWERs:** mentioned (section "Where people and things stand", rule 4, effect on camera A: 4.1 % at the old spot, camera A moved to x = -49 with lens 36 in). Numbers verified (section 2).
- **Tripod feet rule:** concrete and followable: one leg straight away from the wall, the other two 60 deg either side pointing toward the wall, leg radius about 20 in gives feet 10 in toward the wall, so 12 in out from the OUTSIDE face keeps 2 in; general rule R/2 + 2 in; tape the three foot spots first. The lateral feet (17 in either side of the plumb spot) at B stay outside the alliance area limits (y about 75.5 vs 48.5). Gap: if R is larger the doc says to re-run `recommend()` with `TRIPOD_CLEARANCE_IN`, which an operator cannot do ("ask the developer"); assumes 20 in at both 20 in and 36 in lens heights, a 20 in lens height and a 20 in radius both flagged VERIFY.
- **Alliance areas:** now correct. Field Setup Guide 8.5 (page 15; text and figure `evidence/refute/dod9_3/fsg/p15_3_Image136.png`): areas are adjacent to the field perimeter on the left (red) and right (blue) SIDE walls, 54 in deep, about 97 in wide, aligned to tile seams 1 and 5 (y about -48..+48 for a 6 x 24 in tile field). The doc says exactly that, excludes side-wall spots with |y| <= 48.5 + 3, and states both cameras stand beside the audience wall about 37 in clear (85.5 - 48.5) of the area ends. The earlier drive-team premise is gone from the doc. Not stated: where the audience barrier stands (doc says "VERIFY with the event"). The doc does not tie "red alliance on the left" to "red HIVE at +X" (it says only that standing at the audience wall +X is on your left and marks the mirror check VERIFY).

## 5. Remaining VERIFY / unverified assumptions the operator must check

Listed in the docs (all fine, honestly marked): wall thickness 1.5 in; UBeesize MT60 minimum lens height 20 in; tripod leg radius about 20 in; red HIVE on the left standing at the audience wall (mirror every X if not); where a tripod 12 in outside the audience wall may stand (barrier, spectators); tag readability by detection on real footage (geometry-only: B's 22 px / 51 deg CELL tag, kit tags to 54.4 deg against a 55 deg limit: B tags 100 and 102 sit at 54.4 and 54.0 deg); 144 in vs the CAD's 141.35 in inside size (measure and set `field_size_in`); CELL opening width, crossbar height, panel edges and lean (measure, tell the developer if more than 0.5 in off).

**Not listed anywhere and wrong in effect:** (i) solid CELL bodies hide kit tag 100 (both cameras) and tag 101 (A), and click points 5-7; (ii) the base-tag border ambiguity; (iii) the in-app Cross-check cannot be out-of-sample for A (the doc says so, correctly).

## Verdict table

| Attack | Result |
|---|---|
| 1. Panel model vs STEP; tags on real surfaces | NOT REFUTED (0.000 in difference; tags on the plane inside the trapezoid; 102/103 touch the foot bar end) |
| 2. Map byte-identical; all doc numbers vs `recommend()` | NOT REFUTED (4/4 files identical; every number reproduced) |
| 3a. Kit solve at 1 in / 2 deg placement, 0.25 in / 0.5 deg tags, 30 seeds, both options | NOT REFUTED in the all-tags-visible model: 30/30 under 2 px and under 1 in (both options) |
| 3b. Same with the CELL bodies | **REFUTED**: A reads only tag 103, kit solve for A fails 30/30; the documented primary path does not calibrate camera A |
| 3c. Click method against the new gate | NOT REFUTED as a fallback: about 2 in 3 per camera, 48 % pair first try, 100 % opening center < 1 in |
| 4. Followability | mostly followable; base-tag border ambiguity (27/30) and a stand without dimensions are weaknesses |
| 5. VERIFY items | listed and marked, except the CELL occlusion |

## Files (all under `evidence/refute/dod9_4/`)
`panel_check.py`, `regen.py`, `regen/` (4 regenerated maps), `doc_nums.py/.txt`, `occl.py/.txt`, `doc_pct.py/.txt`, `sim4.py`, `sim4_usb.txt/json`, `sim4_gopro.txt/json`, `click_many.py/.txt`, `tag_los.py/.txt`, `tag_los_bothup.py/.txt`, `click_los.py/.txt`, `sim_occluded.py`, `sim_occluded.txt`, `sim_occluded_usb.json`, `sim_occluded_gopro.json`. (`rec.py` is a copy of the round-3 script, not used for results.)

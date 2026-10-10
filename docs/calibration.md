# Calibration procedure (operator)

No Python and no command line are needed. Everything is done in the app (open `http://127.0.0.1:8765` in a browser) on the **Calibration** tab.

**Two ways to set the camera positions (extrinsics):**
- **Primary: the printed tag kit.** Print four AprilTags, tape them on the four top corners of the HIVE frame, press **Auto-calibrate**. No clicking (section 3A).
- **Fallback: click 8 points** by hand on the picture (section 3B). Use it when the tags cannot be taped on, a tag is hidden, or Auto-calibrate reports an error you cannot fix.
Both need the camera intrinsics first (section 2).

**Targets (PLAN.md M1):** reprojection error under 2 px for every camera and every clicked point; a known point (the CELL opening center) triangulates within 1 in of its CAD value. See section 5 for what you can check without Python.

**Cameras:** `cam0` is camera **A** and `cam1` is camera **B** of [camera_placement.md](camera_placement.md) (both stand outside the audience (+Y) wall: A at x = -36 with the lens 30 in high, B at x = +36 with the lens 12 in high). The Calibration tab shows one card per camera in that order. If you ever swap the cable or device index, the labels swap with it, so re-check which card shows which view.

**Field axes used below:** origin at field center, Z up, **+Y toward the audience** (the audience-side CELL), X along the red/blue axis. The red HIVE is at X = +12.75 (the +X half), blue at -12.75. Standing at the audience wall facing the field, +X (red) is on your left. The app assumes the red HIVE's audience-side CELL is the **up** CELL during calibration. Set the HIVE that way before you click anything (top bar, **Set HIVE state**).

## 0. Before you start (do this once, 5 minutes, not part of the 10 minute budget)

1. **Print the checkerboard.** In the browser open `http://127.0.0.1:8765/api/calib/checkerboard.pdf` (the app generates it; it is the 10x7 square board, 1.00 in squares). Print at **100% / Actual size** on letter (A4 fallback). Do not choose "fit to page".
2. Measure one printed square with a ruler: it must be **1.00 in**. Glue the page flat on a rigid board (foam core). A curled or tilted-in-the-glue board ruins intrinsics.
3. **Tape-measure the real HIVE** once and write the numbers down: CELL opening width (model: 20 in), frame width in X (model: 49.46 in), frame depth in Y (model: 38.95 in), height of the frame's top bars (model: 63.95 in, an assumption), height of the up-CELL opening center (model: 59.55 in). Every number marked VERIFY in `hiveshot/field_constants.py` and `hiveshot/field.py` is a CAD guess until you have compared it. If a measurement differs by more than about 0.5 in from the model, tell the developer before calibrating: the extrinsics can only be as accurate as these numbers.
4. Cameras on their marked tripod spots, aimed per camera_placement.md, settings locked (resolution, lens mode, focus, exposure). **Changing any of these later invalidates the intrinsics.**

4b. **Print the tag kit** (for section 3A). In the browser open `http://127.0.0.1:8765/api/calib/tags.pdf`. It is 2 letter-size pages, landscape, two tags per page: AprilTag 36h11 ids 100 to 103, each **4.00 in** square, labeled with the frame corner it belongs to and an arrow "THIS EDGE UP". Print at **100% / Actual size** (not "fit to page") and check the line at the bottom of each page with a ruler: it must measure **4.00 in**. Cut each tag out **leaving the white border (0.5 in or more)**; the camera needs that white margin to see the tag. Glue or tape each tag flat and wrinkle-free on a stiff card the size of the tag plus its white border; matte paper is best (glossy paper glares).

## 1. Timeline (10 minutes for a full calibration)

| Minute | Step |
|---|---|
| 0:00 - 1:00 | Start the app, **Pipeline start**, open the **Calibration** tab. Confirm both cards show a picture (click **Refresh image**). |
| 1:00 - 4:00 | Section 2, intrinsics, `cam0` then `cam1` (about 90 s each). Skip this when lens, resolution and zoom are unchanged since the last good calibration. |
| 4:00 - 6:00 | Section 3A, extrinsics with the tag kit: tape on the four tags (1 minute, they can stay taped between sessions), press **Auto-calibrate** (a few seconds). Fallback 3B instead: 8 clicks and **Solve extrinsics** per camera, about 2 minutes each, so extrinsics end at about 8:00. |
| 6:00 - 10:00 | Section 4, accept or redo, then section 5 (with the click method the check starts at 8:00). |

A re-calibration after bumping a tripod skips section 2 and takes about 5 minutes.

## 2. Intrinsics (per camera, once per lens / resolution / zoom setting)

1. A human holds the printed board in front of the camera. Look at the Calibration tab card for that camera.
2. Click **Start intrinsics**. The app grabs a frame about every half second.
3. For 20 to 30 seconds, move the board slowly: fill the whole frame including the corners, tilt it up to about 45 degrees, vary the distance (about 2 to 5 ft), keep the whole board in view and sharp. Do not cover the board with fingers.
4. Click **Stop intrinsics**. The card shows `Intrinsics: reprojection RMSE x.xxx px, N frames`.
5. **Accept** if RMSE is **under 2 px** (typical 0.3 to 0.8 px) and N is **at least 8** (aim for 25 or more). Otherwise **Start intrinsics** again and move the board through more of the frame. An error message "at least 8" means too few frames showed the whole board.

Saving new intrinsics marks that camera's old extrinsics **stale**: redo section 3 for it.

## 3A. Extrinsics with the tag kit (primary; both cameras at once)

The four tags mark the four top corners of the HIVE frame. All cameras that can see enough tags are solved from them.

1. **Tape the tags on, "label up".** Each tag goes on a vertical face of the frame that **faces the audience (+Y)**, with the arrow "THIS EDGE UP" pointing up (the printed TAG number and name are then readable upright). The tag's **outer top corner sits exactly on the frame corner** and the tag hangs down and inward along the frame, so the tag is flush with the top edge and with the end of the bar (a tag half hanging in the air does not work). Which tag goes where:

| Tag | Frame corner (field axes) | Where it is on the real HIVE |
|---|---|---|
| 100 | (-X, +Y) | audience-side top bar, **blue** end (red HIVE is on the +X side) |
| 101 | (+X, +Y) | audience-side top bar, **red** end |
| 102 | (-X, -Y) | far-side top bar, blue end, on the face that looks toward the audience |
| 103 | (+X, -Y) | far-side top bar, red end, on the face that looks toward the audience |

   Corner positions come from `GET /api/calib/tags` (tag ids, size, center and corner coordinates); the frame size and top height are CAD guesses (VERIFY), so tape-measure where the real frame corners are (section 0 step 3). A tag mounted 1 in off its corner moves the camera pose by about as much.
2. **Keep the tags clean and flat.** No tape over the black-and-white pattern, no shadow across a tag, nobody standing in front. Lighting even; no glare on the paper.
3. In the app, **Calibration** tab, click **Refresh image** on each camera card. Each tag must appear as a clear black-and-white square. The Setup status shows which tag ids each camera sees.
4. Click **Auto-calibrate**. Per camera the card shows `RMSE x.xxx in`, the tags used (for example `100, 101, 102, 103`) and `reprojection x.xx px`.
5. **Accept** if it uses **at least 3 tags** (all 4 is best) and the reprojection error is **under 2 px** (typically 0.3 to 1 px) and the RMSE is **under 0.25 in**. With only 2 tags the pose is weak (expect about 1 to 2 in of error): it still saves, but prefer to fix the missing tag and run again.
6. If it says "only 1 tag visible: 100; need 2" (or "no known tags visible"): look at the picture, find which tags are hidden by the HIVE or too dark/blurred, move the tag a little onto a visible part of the same corner or fix the lighting, click **Refresh image**, and run again. If a camera cannot see 2 tags, use the click method (3B) for that camera.
7. Calibration is saved automatically (`calibration.json` in the data folder). Press **Auto-calibrate all** (or run it on each camera) after every tripod move.
8. **The HIVE's own tags help.** Every CELL carries four official AprilTags on its underside, just below the opening (red audience CELL: ids 34 to 37, red far CELL: 30 to 33, blue 38 to 41 and 42 to 45). Their positions are computed from the official CAD-based field model for both cells in the current HIVE state (`field.hive_tag_corners`), so they count as extra known tags: with `hive_tags` on, Auto-calibrate uses them together with the kit (simulated pose error under 0.1 in with all eight). On their own, without the printed kit, they give only a **coarse** pose (simulated 0.7 to 2.6 in and up to 2 deg, because the four tags sit in one small row): fine for a first check or if the kit is lost, not for final calibration. The cameras cannot see the down CELL's tags (they face up and away), so only the up CELL's tags are normally used. The learn step (`learn_hive_tags`, triangulating the tags from two calibrated cameras) is a **verification** of the model on the real field: it reports the error of every learned tag against its computed position. Tags are only valid while the HIVE is in the state they were computed for: do not calibrate from them while the HIVE is mid-tip.

## 3B. Extrinsics by clicking 8 points (fallback; per camera, after the final tripod placement; redo if a camera moves)

The picture is the live camera view. The 8 points are all **in the air on the HIVE**: the floor is not in frame from the recommended camera spots, and that is expected. The list on the right of each card says which point to click next; the number appears on the picture after each click.

1. Make sure the HIVE is untouched, the red HIVE's audience-side CELL is up, and nobody stands in front of either camera. Click **Refresh image**.
2. Click the 8 points **in this order** (the same order and names on the card):

| # | Name on the card | What it is | Where it is in the picture (GoPro / Arducam, percent from the left, percent from the top) |
|---|---|---|---|
| 1 | Red HIVE up-CELL opening, high-left corner | upper -X corner of the red up-CELL opening (the high edge is the one farther from the audience) | `cam0`: 63/42 or 63/46. `cam1`: 47/62 or 48/62 |
| 2 | Red HIVE up-CELL opening, high-right corner | upper +X corner of the opening | `cam0`: 53/48 or 55/52. `cam1`: 36/55 or 38/56 |
| 3 | Red HIVE up-CELL opening, low-right corner | lower +X corner (the low edge is the one nearest the audience) | `cam0`: 51/58 or 52/61. `cam1`: 36/62 or 38/63 |
| 4 | Red HIVE up-CELL opening, low-left corner | lower -X corner | `cam0`: 61/53 or 61/56. `cam1`: 49/70 or 49/69 |
| 5 | HIVE frame top corner (-X, +Y) | top of the frame, blue side, audience side | `cam0`: 81/26 or 79/33. `cam1`: 63/68 or 61/67 |
| 6 | HIVE frame top corner (+X, +Y) | top of the frame, red side, audience side | `cam0`: 50/48 or 52/52. `cam1`: 36/51 or 38/53 |
| 7 | HIVE frame top corner (-X, -Y) | top of the frame, blue side, far side | `cam0`: 90/45 or 87/48. `cam1`: 51/83 or 51/80 |
| 8 | HIVE frame top corner (+X, -Y) | top of the frame, red side, far side | `cam0`: 63/56 or 63/59. `cam1`: 29/72 or 32/71 |

   Picture description. Both cameras stand outside the audience wall and look up across the field toward the HIVE (`cam0` from x = -36, 30 in high, toward +X and -Y; `cam1` from x = +36, 12 in high, toward -X and -Y). The up-CELL opening is a tilted rectangle in the middle area of the picture (right of the middle in `cam0`, left of it in `cam1`), about 20 in wide and 14 in tall in its own plane. In both cameras the +X (red) side of every object is on the **left** of the picture and the -X side on the right. The audience-side top bar of the frame (points 5 to 6) runs from the upper right down to the lower left at about 21 degrees in `cam0`, and from the lower right up to the upper left at about 20 degrees in `cam1`. Points 1 and 5 are about 8 in apart in real life (about 50 to 90 px), so click the opening's own corner for 1 and the frame bar's end for 5. Just below the opening you can see the CELL's AprilTag sticker (four small squares); it is not one of the 8 points. In `cam0` point 7 is the nearest to the right edge of the picture.

   "left" / "right" in the CELL names mean the **-X / +X side** of the field, not the side of the picture. From both recommended camera spots, "left" appears on the right of the picture.

3. Click as close to the exact corner as you can. Zoom the browser (Ctrl and +) if needed: the click position is converted to full-resolution pixels. Mistake? **Undo point** removes the last click; **Clear** starts over.
4. Click **Solve extrinsics**. The card shows `RMSE x.xxx in` and one `error px` line per point.
5. **Accept** if the RMSE is **under 0.25 in** (about 2 px at these distances; good results are under 0.12 in) and **every point is under 2 px**. One point far above the others is a bad click or a model error: click it again (**Clear**, redo the 8 points), then compare the physical position with the table above. Two or more bad points that all lie on the frame (5 to 8) mean the frame measurements from section 0 do not match the model; tell the developer. If you cannot recognize a point because it is hidden behind part of the HIVE, do not guess: stop and report which point and which camera.
6. Repeat for the other camera. Calibration is saved automatically after each solve (`calibration.json` in the data folder).

## 4. Redo rules

- Camera moved, tripod bumped, new aim: redo section 3A (or 3B) for that camera.
- New resolution, lens mode, zoom or focus: redo section 2, then section 3A (or 3B).
- A **calibration mismatch (n)** tag at the top means a camera now sends a different image size than the one it was calibrated at: fix the camera setting or redo section 2.

## 5. Check the result without Python

1. Both cards: RMSE under 0.25 in, all points under 2 px.
2. The **Current calibration** box at the bottom shows `stale: false` for both cameras.
3. Throw or drop 3 test balls through the up CELL. In the **Replay** tab each ball must be tracked from both cameras over the whole flight and its 3-D track must end at the CELL opening in the viewer. If a track ends clearly away from the opening (more than about one ball diameter, 3 in), the model numbers (section 0, step 3) or a click are wrong.
4. The strict "within 1 in of CAD" triangulation check (clicking one more known point in both cameras and triangulating it) has no button in the app. It is run by the developer from the test suite (`tests/test_placement.py` simulates it: under 0.2 in at 0.5 px click noise). Absolute accuracy on the real field is limited by how well the HIVE and frame numbers in the model match the real HIVE (all VERIFY).

Save a copy of `calibration.json` (data folder) after every good calibration.

## Appendix: developer notes

- The 8 points come from `hiveshot.calib_targets.field_reference_points()` (`reference_point_names()` lists their names). The four CELL corners are read from `hiveshot.field.cell_opening_polygon`; the frame corners are the top-bar ends of `hiveshot.field.hive_frame_wireframe()`. A test fails if either drifts from `field.py`.
- `calib_targets.write_field_point_sheet("docs/field_points.md")` writes a printable table of the 8 points with coordinates.
- `calib_targets.write_checkerboard_pdf(path)` is what the checkerboard route serves.
- Tag kit: `hiveshot.tagkit` (`KIT_TAGS`, `tag_corners_xyz`, `tag_defs()`, `tags_json()`, `write_tag_sheet_pdf(path)`, `tag_sheet_pdf_bytes()`); solver `calib.solve_extrinsics_from_tags(intr, image, tag_defs, cam_id, min_tags=2)` returns `(extrinsics, {tags_used, tags_missing, reprojection_px, max_corner_px, rmse_in})`. Tag ids 100 to 103 are the frame top corners 5 to 8 of the click list. HIVE tags: `tagkit.hive_tag_corners_all(alliance, state)` (both cells), `up_cell_tag_corners`, `hive_tag_defs(alliance, state, learned)` (computed tags of both cells; learned only fills ids without a computed position), `combined_tag_defs(...)` (kit + HIVE tags in one `tag_defs`), `learn_hive_tags(..., alliance=, state=)` (also reports `error_vs_computed_in` for the up cell), `up_cells_from_tags` and `infer_hive_state` (right-side-up cluster = up CELL, tag-up vector z > 0, the SDK's |roll| < 90 deg; cross-checked against the row height vs the 43.95 in pivot). Orientation convention (vertical plane facing +Y, flush mount, cv2.aruco corner order) is documented at the top of `hiveshot/tagkit.py`. Simulated accuracy (`tests/test_tagkit.py`, recommended poses, synthetic images): 4 tags within 0.15 in / 0.07 deg, 3 tags within 0.3 in, 2 tags up to about 2 in / 1 deg.
- Optional: `detect_apriltags` + `solve_extrinsics_from_apriltags` once the real tag geometry is verified (the bundled layout is a placeholder).

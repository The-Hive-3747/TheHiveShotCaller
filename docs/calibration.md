# Calibration procedure (operator)

No Python and no command line are needed. Everything is done in the app (open `http://127.0.0.1:8765` in a browser) on the **Calibration** tab.

**Two ways to set the camera positions (extrinsics):**
- **Primary: the printed tag kit.** Print four AprilTags, tape them on the HIVE frame (two on the audience logo panel at the crossbar ends, two standing at the audience-side base corners), measure where they are with a tape, press **Auto-calibrate**. No clicking (section 3A).
- **Fallback: click 8 points** by hand on the picture: the corners of the two up CELL openings (section 3B). Use it when the tags cannot be taped on, a tag is hidden, or Auto-calibrate reports an error you cannot fix.
Both need the camera intrinsics first (section 2).

**Targets (PLAN.md M1):** reprojection error under 2 px for every camera and every clicked point; a known point (the CELL opening center) triangulates within 1 in of its CAD value. The **Cross-check** button (section 5) tests the second one.

**Cameras:** `cam0` is camera **A** and `cam1` is camera **B** of [camera_placement.md](camera_placement.md): both stand outside the audience (+Y) wall in its corners, lens 20 in high: A in the **-X corner**, B in the **+X corner**. B is the "tag reader" that sees the CELL's own AprilTags. The Calibration tab shows one card per camera in that order. If you ever swap the cable or device index, the labels swap with it, so re-check which card shows which view.

**Field axes used below:** origin at field center, Z up, **+Y toward the audience** (the audience-side CELL), X along the red/blue axis. The red HIVE is at X = +12.75 (the +X half), blue at -12.75. Standing at the audience wall facing the field, +X (red) is on your left. **Set the HIVE to its match-start state before calibrating** (top bar, **Set HIVE state**): red HIVE audience CELL up, blue HIVE far CELL up. The HIVE frame is the official A-frame (not a box): a foot bar on the tiles at each X end, legs leaning inward, a 24 in crossbar along X at 41.45 in; the logo panels stand in front of the crossbar on the audience and far sides.

## 0. Before you start (do this once, 5 minutes, not part of the 10 minute budget)

1. **Print the checkerboard.** In the browser open `http://127.0.0.1:8765/api/calib/checkerboard.pdf` (the app generates it; it is the 10x7 square board, 1.00 in squares). Print at **100% / Actual size** on letter (A4 fallback). Do not choose "fit to page".
2. Measure one printed square with a ruler: it must be **1.00 in**. Glue the page flat on a rigid board (foam core). A curled or tilted-in-the-glue board ruins intrinsics.
3. **Measure your field and the HIVE** once and write the numbers down: the field wall to wall (inside face to inside face; the app's `field_size` setting defaults to 144 in, the CAD value is 141.35 in: set it to your measurement), the wall thickness, the CELL opening width (model: 20 in), the **height of the crossbar centerline above the tiles (model: 41.45 in)**, the crossbar length (model: 24 in, ends at x = +-12.0 from the HIVE's center), the **logo panels**: top edge height (model: 40.0 in), width (model: 30.1 in) and how far the audience face is in front of the frame's center line (model: 4.3 in), the **foot bar** outer face (model: 24.73 in from the center line) and its end (model: 19.47 in from the other center line, 2.15 in high), and the height of the up-CELL opening center (model: 59.55 in). If a measurement differs by more than about 0.5 in from the model, tell the developer before calibrating: the extrinsics can only be as accurate as these numbers.
4. Cameras on their marked tripod spots, aimed per camera_placement.md, settings locked (resolution, lens mode, focus, exposure). **Changing any of these later invalidates the intrinsics.**

4b. **Print the tag kit** (for section 3A). In the browser open `http://127.0.0.1:8765/api/calib/tags.pdf`. It is 4 letter-size pages, portrait, **one tag per page**: AprilTag 36h11 ids 100 to 103, each **6.00 in** square, labeled with the frame feature it belongs to, an arrow "THIS EDGE UP" and short taping instructions. Print at **100% / Actual size** (not "fit to page") and check the line at the bottom of each page with a ruler: it must measure **6.00 in**. Cut each tag out **leaving the white border (0.5 in or more; the page leaves 1.25 in on each side)**; the camera needs that white margin to see the tag. Glue each tag flat and wrinkle-free on a stiff card (foam core) the size of the tag plus its white border; matte paper is best (glossy paper glares). Tags 102 and 103 need a small stand: a card easel, or a wedge of foam core that holds the card 20 deg back from vertical.

## 1. Timeline (10 minutes for a full calibration)

| Minute | Step |
|---|---|
| 0:00 - 1:00 | Start the app, **Pipeline start**, open the **Calibration** tab. Confirm both cards show a picture (click **Refresh image**). |
| 1:00 - 4:00 | Section 2, intrinsics, `cam0` then `cam1` (about 90 s each). Skip this when lens, resolution and zoom are unchanged since the last good calibration. |
| 4:00 - 6:00 | Section 3A, extrinsics with the tag kit: tape on and measure the four tags (they can stay taped between sessions, the base tags must be re-checked each time), press **Auto-calibrate** (a few seconds). Fallback 3B instead: 8 clicks and **Solve extrinsics** per camera, about 2 minutes each, so extrinsics end at about 8:00. |
| 6:00 - 10:00 | Section 4, accept or redo, then section 5 (**Cross-check**; with the click method the check starts at 8:00). |

A re-calibration after bumping a tripod skips section 2 and takes about 5 minutes.

## 2. Intrinsics (per camera, once per lens / resolution / zoom setting)

1. A human holds the printed board in front of the camera. Look at the Calibration tab card for that camera.
2. Click **Start intrinsics**. The app grabs a frame about every half second.
3. For 20 to 30 seconds, move the board slowly: fill the whole frame including the corners, tilt it up to about 45 degrees, vary the distance (about 2 to 5 ft), keep the whole board in view and sharp. Do not cover the board with fingers.
4. Click **Stop intrinsics**. The card shows `Intrinsics: reprojection RMSE x.xxx px, N frames`.
5. **Accept** if RMSE is **under 2 px** (typical 0.3 to 0.8 px) and N is **at least 8** (aim for 25 or more). Otherwise **Start intrinsics** again and move the board through more of the frame. An error message "at least 8" means too few frames showed the whole board.

Saving new intrinsics marks that camera's old extrinsics **stale**: redo section 3 for it.

## 3A. Extrinsics with the tag kit (primary; both cameras at once)

The four tags mark real features of the frame, and the solve trusts their positions: **a tag taped 1 in off its place moves the camera pose by several inches** (table below). Tape each tag where the table says, then **measure it with a tape and fix it until it is within 0.25 in (and its tilt within 0.5 deg)**.

1. **Tape the tags on, "label up"** (the arrow "THIS EDGE UP" points up, so the printed TAG number and name read upright). All four tags face the audience side (+Y). Positions in inches, in the field axes (X along the red/blue axis, Y toward the audience, Z up from the tiles), HIVE centered on the field:

| Tag | Where | What to measure (each within 0.25 in) |
|---|---|---|
| 100 | **audience (+Y) face of the logo panel**, centered on the **-X crossbar end** | the tag is vertical; its **top edge is flush with the panel's top edge (40.0 in above the tiles)**; it covers x = -15 to -9 (centered 12.0 in from the frame's center line on the -X side); its face is the panel face (4.3 in in front of the frame's center line toward the audience) |
| 101 | audience (+Y) face of the logo panel, centered on the **+X crossbar end** (the red end) | same, x = +9 to +15 |
| 102 | **stands on the tile** at the audience-side **-X base corner** (blue side) of the frame, leaning back | bottom edge on the tile at **20.25 in** from the frame's center line toward the audience (0.8 in beyond the end of the foot bar); outer edge flush with the foot bar's outer face (covers x = -24.73 to -18.73); tag **leans back 20 deg** from vertical (top edge 2.05 in nearer the frame, 5.6 in above the tile) and rests against the top edge of the foot bar end (the foot bar is 2.15 in high) |
| 103 | stands on the tile at the audience-side **+X base corner** (red side) | same, x = +18.73 to +24.73 |

   Why the panel and not the crossbar: the 1 in crossbar sits behind the logo panel (the panel is 1.5 to 4.3 in in front of it and covers z = 34 to 40 in), so a tag hung from the crossbar would be hidden. The tag fills the panel's 6 in height (a 6 in tag overhangs the panel's bottom edge by 0.05 in). A tag at x = +-12 spans x = 9 to 15, inside the panel (+-15.07). **Why the base tags are tilted back:** the cameras are only 20 in high, so a tag lying flat or standing vertical on the tiles is seen at a grazing angle; leaning it back 20 deg faces it toward them.
   Corner positions of the four tags (and their normals) come from `GET /api/calib/tags`. If your measurements of the real frame (section 0 step 3) differ from the model, tell the developer: the tags' model positions come from the CAD frame.
2. **Keep the tags clean and flat.** No tape over the black-and-white pattern, no shadow across a tag, nobody and **no robot** inside the walls (a robot can hide the base tags). Lighting even; no glare on the paper.
3. In the app, **Calibration** tab, click **Refresh image** on each camera card. Each tag must appear as a clear black-and-white square (the base tags near the bottom of the picture). The Setup status shows which tag ids each camera sees.
4. Click **Auto-calibrate**. Per camera the card shows `RMSE x.xxx in`, the tags used (for example `100, 101, 102, 103`) and `reprojection x.xx px`.
5. **Accept** if it uses **at least 3 tags** (all 4 is best; with the GoPro `cam1` sees tag 103 too close to the bottom edge and uses 100, 101 and 102) and the reprojection error is **under 2 px** and the RMSE is **under 0.25 in**. With only 2 tags the pose is weak (expect about 1 to 2 in of error): it still saves, but prefer to fix the missing tag and run again. **A reprojection error of 1.5 to 3 px with tags that look fine usually means a tag is mounted off its model position: re-measure the tags before accepting.**
6. If it says "only 1 tag visible: 100; need 2" (or "no known tags visible"): look at the picture, find which tags are hidden or too dark/blurred, fix the lighting or the stand, click **Refresh image**, and run again. If a camera cannot see 2 tags, use the click method (3B) for that camera.
7. Calibration is saved automatically (`calibration.json` in the data folder). Press **Auto-calibrate all** (or run it on each camera) after every tripod move. Then press **Cross-check** (section 5).
8. **The HIVE's own tags help.** Every CELL carries four official AprilTags on its underside, just below the opening (red audience CELL: ids 34 to 37, red far CELL: 30 to 33, blue 38 to 41 and 42 to 45). Their positions are computed from the official CAD-based field model for both cells in the current HIVE state (`field.hive_tag_corners`), so they count as extra known tags: with `hive_tags` on, Auto-calibrate uses them together with the kit. On their own, without the printed kit, they give only a **coarse** pose (simulated 0.7 to 2.6 in and up to 2 deg, because the four tags sit in one small row): fine for a first check or if the kit is lost, not for final calibration. The cameras cannot see the down CELL's tags (they face up and away), so only the up CELL's tags are normally used. Only `cam1` (B, the tag reader, 51 degrees off the sticker normal, tag edges 22 to 27 px) reads the sticker; `cam0` sees it at 57 degrees, too oblique, so `cam0` is calibrated from the printed kit (it reads all four kit tags). The learn step (`learn_hive_tags`, triangulating the tags from two calibrated cameras) is a **verification** of the model on the real field: it reports the error of every learned tag against its computed position. Tags are only valid while the HIVE is in the state they were computed for: do not calibrate from them while the HIVE is mid-tip.

**What a mounting error costs** (simulation at the recommended poses, 20 runs per case, tags displaced by the error vector and tilted by the angle error, the solver still using the model positions; `evidence/refute/dod9_kit_mounting_sim.json`):

| Tag mounting error | Camera position error (median / max) | Rotation error (median / max) | Reprojection error shown | Runs under 2 px | CELL opening center error (median / max) |
|---|---|---|---|---|---|
| exact | 0.14 / 0.21 in | 0.08 / 0.11 deg | 0.8 px | 20 / 20 | 0.04 / 0.04 in |
| 0.25 in, 0.5 deg | 1.0 / 2.0 in | 0.55 / 1.0 deg | 1.0 px | 20 / 20 | 0.28 / 0.54 in |
| 0.5 in, 1 deg | 2.1 / 4.1 in | 1.1 / 2.0 deg | 1.7 px | 9 / 20 | 0.51 / 1.1 in |
| 1 in, 2 deg | 4.2 / 8.0 in | 2.0 / 3.9 deg | 3.2 px | 0 / 20 | 1.1 / 2.3 in |

So: tape-measure each tag to **0.25 in**. At 0.5 in the 2 px gate fails in most runs, at 1 in it always fails and the pose is several inches off.

## 3B. Extrinsics by clicking 8 points (fallback; per camera, after the final tripod placement; redo if a camera moves)

The 8 points are the **corners of two CELL openings that exist on the field**: the red HIVE's audience-side CELL (up at match start) and the blue HIVE's far-side CELL (also up). They are all **in the air on the HIVE**: the floor is not in frame from the recommended camera spots, and that is expected. The list on the right of each card says which point to click next; the number appears on the picture after each click.

1. Make sure the HIVE is untouched, in its match-start state (red audience CELL up, blue far CELL up), and nobody stands in front of either camera. Click **Refresh image**.
2. Click the 8 points **in this order** (the same order and names on the card):

| # | Name on the card | What it is | Where it is in the picture (GoPro / Arducam, percent from the left, percent from the top) |
|---|---|---|---|
| 1 | Red HIVE up-CELL opening, high-left corner | upper -X corner of the red up-CELL opening (the high edge is the one farther from the audience) | `cam0`: 60/24 or 60/30. `cam1`: 40/27 or 44/33 |
| 2 | Red HIVE up-CELL opening, high-right corner | upper +X corner of the opening | `cam0`: 54/29 or 55/35. `cam1`: 31/19 or 37/27 |
| 3 | Red HIVE up-CELL opening, low-right corner | lower +X corner (the low edge is the one nearest the audience) | `cam0`: 52/37 or 53/42. `cam1`: 33/30 or 38/35 |
| 4 | Red HIVE up-CELL opening, low-left corner | lower -X corner | `cam0`: 58/33 or 58/38. `cam1`: 42/36 or 46/40 |
| 5 | Blue HIVE far-CELL opening, high-left corner | upper -X corner of the blue far-CELL opening (the far CELL's open face points away from you, you see its back; click the corners of the opening rim, the end of the CELL box farthest from you; here the high edge is the one nearer the pivot) | `cam0`: 80/21 or 77/27. `cam1`: 40/37 or 44/41 |
| 6 | Blue HIVE far-CELL opening, high-right corner | upper +X corner of that opening | `cam0`: 71/27 or 69/32. `cam1`: 34/33 or 39/38 |
| 7 | Blue HIVE far-CELL opening, low-right corner | lower +X corner (the low edge is the one farthest from the pivot) | `cam0`: 73/37 or 71/41. `cam1`: 32/43 or 37/46 |
| 8 | Blue HIVE far-CELL opening, low-left corner | lower -X corner | `cam0`: 82/33 or 79/37. `cam1`: 38/46 or 43/49 |

   Picture description. Both cameras stand outside the audience wall in its corners, 20 in high, looking across the field and slightly up (`cam0` from the -X corner toward +X and -Y, `cam1` from the +X corner toward -X and -Y). The red up-CELL opening is a tilted rectangle about 20 in wide and 14 in tall in its own plane in the upper middle of the picture (right of the middle in `cam0`, left of it in `cam1`). The blue far-CELL opening is farther away: it appears further to the right than the red one in `cam0` and lower in the picture in `cam1`. In both cameras the +X (red) side of every object is on the **left** of the picture and the -X side on the right. Just below the red opening you can see the CELL's AprilTag sticker (four small squares); it is not one of the 8 points. In `cam0` the far-CELL points 5 and 8 are near the right edge of the picture.

   "left" / "right" in the names mean the **-X / +X side** of the field, not the side of the picture. From both recommended camera spots, "left" appears on the right of the picture.

3. Click as close to the exact corner as you can. Zoom the browser (Ctrl and +) if needed: the click position is converted to full-resolution pixels. Mistake? **Undo point** removes the last click; **Clear** starts over.
4. Click **Solve extrinsics**. The card shows `RMSE x.xxx in` and one `error px` line per point.
5. **Accept** if the RMSE is **under 0.25 in** (about 2 px at these distances; good results are under 0.12 in) and **every point is under 2 px**. With ordinary clicking (about 1.5 px) expect 1 to 2 px; one point far above the others is a bad click: **Clear** and click again, then compare the physical position with the table above. If you cannot recognize a point because it is hidden behind part of the HIVE, do not guess: stop and report which point and which camera.
6. Repeat for the other camera. Calibration is saved automatically after each solve (`calibration.json` in the data folder). Then press **Cross-check** (section 5).

## 4. Redo rules

- Camera moved, tripod bumped, new aim: redo section 3A (or 3B) for that camera.
- A tag moved or knocked (especially the two standing tags): re-measure it, then redo 3A.
- New resolution, lens mode, zoom or focus: redo section 2, then section 3A (or 3B).
- A **calibration mismatch (n)** tag at the top means a camera now sends a different image size than the one it was calibrated at: fix the camera setting or redo section 2.

## 5. Check the result

1. Both cards: RMSE under 0.25 in, all points under 2 px.
2. The **Current calibration** box at the bottom shows `stale: false` for both cameras.
3. **Cross-check button** (top card of the Calibration tab, "Compares triangulated reference points with the field model"). Pipeline running and both cameras calibrated. It triangulates known points from both cameras and compares each with its known field position. **It is out-of-sample by default**: it uses tags that no calibration solve used. After a kit solve it checks the HIVE's own tags (their computed positions on the CELLs), after a HIVE-tags-only solve it checks the kit tags, after a click solve it checks every visible tag. The result shows one row per point (measured position, expected position, error in inches) and a line "Max error x.xx in": **green (under 1 in) is the M1 target**; red means the calibration (or a tag position) is off. The line says which tags were held out (for example "HIVE tags"); if nothing could be held out (for example no unused tag is visible in both cameras) it falls back to re-measuring the points the solves used and shows a warning that this is **in-sample**: a green result then only shows that the solve is self-consistent, not that it is right. A 422 error means no point is visible in both cameras; 409 means a camera is not calibrated yet.
4. Throw or drop 3 test balls through the up CELL. In the **Replay** tab each ball must be tracked from both cameras over the whole flight and its 3-D track must end at the CELL opening in the viewer. If a track ends clearly away from the opening (more than about one ball diameter, 3 in), the model numbers (section 0, step 3), a tag position or a click is wrong.

Absolute accuracy on the real field is limited by how well the HIVE and frame numbers in the model match the real HIVE (measure them, section 0 step 3) and, for the kit, by how well each tag is placed (0.25 in).

Save a copy of `calibration.json` (data folder) after every good calibration.

## Appendix: developer notes

- The 8 click points come from `hiveshot.calib_targets.field_reference_points()` (`reference_point_names()` lists their names, the Calibration tab fetches them from `GET /api/calib/points`): the corners of `field.cell_opening_polygon` for the red audience CELL and the blue far CELL, both up at match start. A test fails if they drift from `field.py`. The earlier frame "top corners" (a box at 64 in) do not exist on the CAD A-frame and are gone.
- `calib_targets.write_field_point_sheet("docs/field_points.md")` writes a printable table of the 8 points with coordinates.
- `calib_targets.write_checkerboard_pdf(path)` is what the checkerboard route serves.
- Tag kit: `hiveshot.tagkit` (`KIT_TAGS`, `kit_tags(size_in)`, `tag_corners_xyz`, `tag_normal_xyz`, `tag_defs()`, `tags_json()`, `write_tag_sheet_pdf(path, size_in)`, `tag_sheet_pdf_bytes()`); solver `calib.solve_extrinsics_from_tags(intr, image, tag_defs, cam_id, min_tags=2)` returns `(extrinsics, {tags_used, tags_missing, reprojection_px, max_corner_px, rmse_in})`. Tags 100/101 sit on the audience face of the CAD logo panel at the crossbar ends (x = +-12.0, top edge 40.02), tags 102/103 stand at the audience-side base corners (`field.frame_reference_points`), leaning back `BASE_TILT_DEG` = 20 deg against the foot bar end. The default size is `DEFAULT_TAG_SIZE_IN` = 6.0 in (up to 7.5 in fits a letter page with its quiet zone). HIVE tags: `tagkit.hive_tag_corners_all(alliance, state)` (both cells), `up_cell_tag_corners`, `hive_tag_defs(alliance, state, learned)` (computed tags of both cells; learned only fills ids without a computed position), `combined_tag_defs(...)` (kit + HIVE tags in one `tag_defs`), `learn_hive_tags(..., alliance=, state=)` (also reports `error_vs_computed_in`), `up_cells_from_tags` and `infer_hive_state` (right-side-up cluster = up CELL, tag-up vector z > 0, the SDK's |roll| < 90 deg; cross-checked against the row height vs the 43.95 in pivot). Orientation convention (cv2.aruco corner order, tilted base tags) is documented at the top of `hiveshot/tagkit.py`. Simulated accuracy (`tests/test_tagkit.py`): readable 6 in kit tags give every camera a pose within 0.21 in / 0.13 deg when taped exactly; taping error maps to pose error as in the table in section 3A (`evidence/refute/dod9_kit_mounting_sim.py`).
- Optional: `detect_apriltags` + `solve_extrinsics_from_apriltags` once the real tag geometry is verified (the bundled layout is a placeholder).

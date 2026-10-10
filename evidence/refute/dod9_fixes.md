# DoD 9 fixes (response to evidence/refute/dod8_9_1.md, DoD 9 section)

Owner: worker. Files changed: hiveshot/calib_targets.py, hiveshot/placement.py, docs/calibration.md, docs/camera_placement.md, docs/camera_placement.svg, docs/camera_placement.png, tests/test_calib.py, tests/test_placement.py. hiveshot/field.py untouched.

## Finding to fix to test

| # | Finding | Fix | Test |
|---|---|---|---|
| 1 | calib_targets put the CELL opening center at y=15.44, field.py at y=24.25 (8.8 in apart) | `up_cell_opening_corners()` no longer derives anything: it returns corners of `field.cell_opening_polygon(alliance, which, HiveState(alliance, which))`. `fc.BEAM_HALF_LENGTH` is no longer used. The point-sheet text now quotes field.py values. New CELL corners: y 20.73 (high edge) and 27.76 (low edge), center y 24.25, z 53.50 to 65.60. | `tests/test_calib.py::test_cell_reference_points_equal_field_polygon` (each of the 4 CELL points is within 1e-6 of a field.py polygon corner, all 4 corners used once, mean = `cell_opening_plane` center, center y = `field.OPENING_CENTER_ABS_Y`) |
| 2 | Only 4 of 8 points inside the image from the recommended poses | New 8 points: 4 up-CELL corners + 4 HIVE frame top corners. Verified programmatically with `placement.recommend()` + `camera_from_pose`. Tile intersections are NOT usable (see "Deviation"). `field_reference_points()` signature unchanged, `reference_point_names()` added. | `tests/test_placement.py::test_all_reference_points_inside_both_images[gopro,usb]` (all 8 inside 1920x1080, depth > 1 in, 20 px margin, cams A and B); `tests/test_calib.py::test_frame_reference_points_are_wireframe_corners`; `test_reference_point_names_helper`; `tests/test_placement.py::test_extrinsics_from_reference_points_at_recommended_poses[gopro,usb]` (0.5 px click noise, 5 seeds: RMSE < 2 px and CELL center triangulation < 1 in against field.py) |
| 3 | Sheet said "X toward the audience side" | Sheet now says "+Y toward the audience side (the audience-side CELL), X along the red/blue axis (red HIVE at X = -12.75)" | `tests/test_calib.py::test_point_sheet_axes_match_field_py` |
| 4 | calibration.md was Python calls | Rewritten as an app-only procedure (Calibration tab buttons: Refresh image, Undo point, Clear, Solve extrinsics, Start/Stop intrinsics), ordered 8-point table with expected on-screen position in percent, picture description, RMSE thresholds, 10 minute timeline. Written as if `GET /api/calib/checkerboard.pdf` exists (see request below). | Doc check (manual diff); percentages recomputed from `recommend()` poses |
| 5 | camera_placement.md gaps | cam0 = A, cam1 = B table; Option B hub advice removed, direct-PC-port requirement stated; yaw (bearing from +X toward +Y) and pitch for A, B, C; aiming method with a floor cross at (-13,+41); +-72 stated as INSIDE face, tripod distances from the OUTSIDE face (assumed 1.5 in wall, VERIFY: 4.5 in out, 8.5 in along); roll check replaced (see Deviation) | `tests/test_placement.py::test_aim_angles_and_outer_face_measurements`, `test_placement_doc_matches_recommend` (doc yaw, pitch, 4.5 / 8.5 in strings equal recommend(); no "powered hub" advice; svg carries the yaw) |
| 6 | SVG/PNG must equal recommend() | Regenerated with `placement.write_map('gopro', ...)`; map legend now shows yaw/pitch and "INSIDE face". Re-run into a temp dir gives identical SHA256 (below). | `tests/test_placement.py::test_map_files_exist_and_agree` |

## New 8 reference points (field frame, inches; click order)

| # | Name (UI/API key) | X | Y | Z | Source |
|---|---|---|---|---|---|
| 1 | Red HIVE up-CELL opening, high-left corner | -22.75 | 20.73 | 65.60 | field.cell_opening_polygon[3] |
| 2 | Red HIVE up-CELL opening, high-right corner | -2.75 | 20.73 | 65.60 | polygon[2] |
| 3 | Red HIVE up-CELL opening, low-right corner | -2.75 | 27.76 | 53.50 | polygon[1] |
| 4 | Red HIVE up-CELL opening, low-left corner | -22.75 | 27.76 | 53.50 | polygon[0] |
| 5 | HIVE frame top corner (-X, +Y) | -24.73 | 19.48 | 63.95 | field.hive_frame_wireframe(): audience-side top bar, segment (-24.73, 19.475, 63.95) to (24.73, 19.475, 63.95) |
| 6 | HIVE frame top corner (+X, +Y) | 24.73 | 19.48 | 63.95 | other end of that segment |
| 7 | HIVE frame top corner (-X, -Y) | -24.73 | -19.48 | 63.95 | far-side top bar, segment (-24.73, -19.475, 63.95) to (24.73, -19.475, 63.95) |
| 8 | HIVE frame top corner (+X, -Y) | 24.73 | -19.48 | 63.95 | other end |

Names of points 1-4 are unchanged ("left/right" = -X/+X side). Points 5-8 replace the old "frame base corner" and "tile intersection" names.

Projected position (percent from left / percent from top), recommended poses, 1920x1080:
- GoPro, A: 66/43, 59/51, 56/63, 63/58, 68/45, 53/60, 89/51, 68/62. B: 43/50, 37/45, 40/57, 46/61, 43/52, 21/36, 29/56, 4/44.
- Arducam, A: 64/44, 58/51, 55/61, 61/57, 66/45, 53/58, 83/51, 66/60. B: 44/50, 39/46, 41/56, 46/59, 44/52, 26/38, 32/55, 11/45.
Smallest margin is B GoPro point 8 at about 80 px from the left edge.

## Deviations from the brief, and why

1. **No tile intersections.** The brief asked for 2 tile intersections in front of the HIVE inside both images. A search over all 24-in seam intersections (x, y in -72..72, z = 0) found none inside either camera at either option (cams look at z=61 from z=36 with pitch 16 to 20 deg; the lower image edge is about 7 deg below horizontal at lens height, so the floor is only visible beyond about 270 in). Replaced by the two far-side top corners of the HIVE frame (also on `hive_frame_wireframe()`), which are inside both images in both options and add 40 in of depth spread for PnP conditioning (the 4 CELL corners are coplanar).
2. **Launch area is not in frame.** The "launch area at the bottom third" aiming hint cannot be given: the launch points (z = 12, y 50 to 66) project at v = 1000 to 2000 px, i.e. below the bottom edge. The doc says so and gives the CELL center position (about 61/54 in A, 42/53 in B) instead.
3. **Roll check.** "HIVE frame horizontal top bar level in preview" is false at these poses: the audience-side top bar (points 5-6) projects at about 30 deg below horizontal in A and 23 deg above horizontal in B (perspective; it runs along the line of sight). The doc gives those expected slopes (+-3 deg) and keeps the level-app roll check.
4. Placement tolerances (computed): shifting yaw/pitch until any of the 8 points leaves a 20 px margin: B GoPro tolerates only about 1.5 deg clockwise yaw (29 deg counter-clockwise), A GoPro about 6.5 deg counter-clockwise. Doc tells the operator what to do if point 8 in B is cut off.

## Known risks (not fixed, VERIFY items)

- FRAME_WIDTH_X, FRAME_DEPTH_Y, HIVE_CENTER_SPACING_X, CELL constants are CAD guesses and `field.FRAME_TOP_Z = PIVOT_HEIGHT + 20` is an explicit assumption. Points 5-8 depend on the frame being a box with those dimensions. Operator step 0.3 of calibration.md asks for a tape measurement.
- Point 5 is only about 3 in from point 1 in space (about 40 px in the image) and point 7 may be partly hidden by the HIVE; the doc warns.
- Wall thickness 1.5 in is an assumption (WALL_THICKNESS_IN).
- hiveshot/app.py and ui/app.js are not owned by this worker and still use the OLD point names (requests below).

## Requests for the lead (files I do not own)

1. **hiveshot/app.py: add `GET /api/calib/checkerboard.pdf`**: build with `calib_targets.write_checkerboard_pdf(tmp_path)` (or `calib_targets._build_pdf(*calib_targets.render_checkerboard())` to avoid a temp file) and return `Response(pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": 'inline; filename="checkerboard.pdf"'})`. calibration.md already refers to this URL. Optional: add `GET /api/calib/points` returning `calib_targets.reference_point_names()`.
2. **ui/app.js `CALIB_POINTS` (lines 7-16) must be updated**, or the extrinsics endpoint returns 422 "unknown reference point name" for points 5-8. Use the names above (or fetch `/api/calib/points`). The app's name lookup (`/api/calib/extrinsics/{cam}`, lowercased) already uses `field_reference_points()`, so no app.py change is needed for the solve itself. Points 1-4 names are unchanged. The UI also says "All 8 points set", which still matches.
3. docs/api.md line 31 refers to "docs field point sheet"; names are listed above and by `reference_point_names()`.
4. Ship the docs in the zip (separate finding, not in my scope).

## Outputs

```
$ .venv\Scripts\python.exe -m pytest tests/test_calib.py tests/test_placement.py -q -rA
(25 passed, 0 failed, 0 skipped; project addopts "-q" suppresses the summary line)
tests/test_calib.py: test_intrinsics_from_corners, test_too_few_frames_raises, test_extrinsics_recovered,
  test_triangulate_two_cameras, test_save_load_roundtrip, test_apriltag_placeholder_ids,
  test_checkerboard_pdf_and_png, test_field_point_sheet, test_real_corner_detection_on_warped_board,
  [new] test_cell_reference_points_equal_field_polygon, test_frame_reference_points_are_wireframe_corners,
  test_reference_point_names_helper, test_point_sheet_axes_match_field_py
tests/test_placement.py: [existing] recommend_pair x2, camera_from_pose, candidates, occlusion, map files, ...
  [new] test_all_reference_points_inside_both_images[gopro], [usb],
  test_extrinsics_from_reference_points_at_recommended_poses[gopro], [usb],
  test_aim_angles_and_outer_face_measurements, test_placement_doc_matches_recommend

$ .venv\Scripts\python.exe -m ruff check hiveshot tests
All checks passed!
```

Monte Carlo (30 seeds, 0.5 px click noise on 8 points and on the CELL center probe, recommended poses): CELL center triangulation error median 0.067 in / max 0.111 in (GoPro), median 0.078 / max 0.129 (Arducam); extrinsics reprojection RMSE max 0.92 px. This is simulation against field.py geometry only; nothing here was measured on a real field.

Map regeneration (write_map('gopro') into a temp dir vs docs/):
- camera_placement.svg SHA256 65937d3a690a48541ceed42d8c7709d1a2199da8d8c2a6bf34c640f99f839c06 (identical)
- camera_placement.png SHA256 4ef80e676665c875fd1497db601eab34df235abb2e9f5b0e3859266d3f0b4fc6 (identical)

Wider run: `pytest -q -m "not build and not live" --ignore=tests/test_build_smoke.py` finished with exit code 0 (199 dots, no failures; includes tests/test_app.py and test_ui_static.py, so the unchanged UI/app still pass). `tests/test_build_smoke.py::test_vc_runtime_dlls_ship_with_bundle[msvcp140.dll]` fails on the dist bundle (the already-known missing plain msvcp140.dll), unrelated to these files and not part of the above.

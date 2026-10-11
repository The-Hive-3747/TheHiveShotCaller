# DoD 9 fixes (response to evidence/refute/dod8_9_1.md, DoD 9 section), current state

This file replaces the first version, which described the early -X layout. It reflects the
CAD-based field (red HIVE at +X, up-CELL opening center (+12.75, 15.77, 59.55), CELL tag row
(+12.75, 13.10, 49.79)), the printed tag kit, and the constrained placement search.

Owned files: hiveshot/calib_targets.py, hiveshot/placement.py, hiveshot/tagkit.py (earlier task),
docs/calibration.md, docs/camera_placement.md/.svg/.png, tests/test_calib.py, tests/test_placement.py,
tests/test_tagkit.py. hiveshot/field.py is the single source of geometry and is not edited by this worker.

## Original findings and where they stand

| # | Finding | Fix | Evidence (tests) |
|---|---|---|---|
| 1 | calib_targets used its own CELL geometry (opening center y=15.44) that disagreed with field.py (24.25 at the time) | `calib_targets.up_cell_opening_corners()` returns corners of `field.cell_opening_polygon`; no separate derivation | `test_calib.py::test_cell_reference_points_equal_field_polygon` (within 1e-6, center = `field.cell_opening_plane`) |
| 2 | only 4 of 8 reference points visible from the recommended poses | 8 points = 4 up-CELL corners + 4 HIVE frame top corners (floor points are out of frame at these poses); `reference_point_names()` added | `test_placement.py::test_all_reference_points_inside_both_images[gopro,usb]` (20 px margin), `test_extrinsics_from_reference_points_at_recommended_poses` |
| 3 | sheet text said "X toward the audience" | now "+Y toward the audience, X along the red/blue axis (red at +12.75)" | `test_calib.py::test_point_sheet_axes_match_field_py` |
| 4 | calibration.md was Python calls | app-only procedure; tag-kit method primary, 8-click fallback; percent-of-image table checked by a test | `test_placement.py::test_calibration_doc_pixel_table_matches_recommend` |
| 5 | camera_placement.md gaps (cam0/cam1, hub advice, yaw/pitch, wall face, roll check) | cam0 = A, cam1 = B, direct PC port per USB camera, yaw and pitch per camera, inside-face convention with 1.5 in wall assumption (VERIFY), in-frame roll check by expected bar slope | `test_placement.py::test_placement_doc_matches_recommend`, `test_aim_angles_and_outer_face_measurements` |
| 6 | SVG/PNG must equal recommend() | regenerated with `placement.write_map` (see hashes below) | `test_placement.py::test_map_files_exist_and_agree` |

## Placement constraints now implemented (hiveshot/placement.py)

`recommend(option)` searches lens heights 20, 24, 30, 36, 48, 58 in (UBeesize MT60 practical minimum 20 in) on the ring outside the wall plus every 12 in along the audience wall, jointly for both lens options so one set of tape marks serves both. Tiers, compared lexicographically:

1. arc coverage >= 90 % in both cameras and mean triangulation angle 75..120 deg (hard)
2. robot-free rays >= 90 % per camera (hard): robot box 18 x 18 x 24 in plus 3 in extension on every horizontal side, centered on each of the six sample launch points; targets = ball positions of the first 0.3 s of that shot (positions still inside the box are skipped), the up-CELL opening center and the tag row center
3. at least one camera reads the CELL tags (sticker < 55 deg off normal, all four tags inside the picture with 60 px margin, tag edge >= 14 px, tag-row ray free of the robot from every launch point), the "tag reader"
4. printed kit readable in both (>= 3 of the 4 six-inch tags, < 55 deg, >= 28 px)
5. all 8 click points in view (60 px margin)
6. not both cameras on the audience wall (allowed only if nothing satisfies 1 to 5)
7. both cameras read the tags (preferred, never traded against 1)

Value within a tier: pair score x tag quality x corner preference (cameras on the audience wall prefer |x| large, the drive team stands at the wall center). Afterwards each camera is re-aimed to the middle of the aim range that keeps its kit, reference points (and tags for the reader) in view.
The best "both cameras read the tags" pair is returned as `recommend()["both_tags_alternative"]` (triangulation relaxed to 60..120 deg) and is not the recommendation.

## Result (same positions for GoPro and Arducam options)

| | Recommended | Best "both cameras read tags" (reported only) |
|---|---|---|
| A (`cam0`) | (-78, +65), lens 30 in; tag angle 66 deg, not a reader; reads kit tags 100, 102, 103 | (-48, +78), lens 20 in; tag angle 52 deg |
| B (`cam1`) | (+65, +78), lens 20 in; tag angle 49 deg, **tag reader**; reads kit tags 101, 102, 103 | (+72, +78), lens 20 in; tag angle 51 deg |
| Mean triangulation angle | 105 deg (GoPro) / 106 deg (Arducam) | 91 deg / 91 deg |
| Both on the audience wall | no | yes |
| Robot-free rays A / B | 100 % / 97 % (CELL and tag rays 100 %) | 98 % / 98 % |

Aims (yaw from +X toward +Y / pitch / aim point): A GoPro 340 / +16 / (12, 32, 58), A Arducam 343 / +16 / (13, 37, 58), B both 218 / +31 / (13, 37, 60). Aim slack at least 5 deg (GoPro A yaw), more elsewhere.
Camera C (optional exit-speed): (+13, +78), lens 58 in, 269 deg / -45 deg.

Sensitivity of the robot model (B, GoPro): extension 0 in: 98 % free; 3 in: 97 %; 6 in: 95 %; 9 in: 86 % (fails the 90 % rule; CELL/tag rays 83 %); 12 in: 75 %.

## Kit size follow-up (4 in to 6 in tags), before / after

The default kit tag size is now a parameter (`size_in`, default `DEFAULT_TAG_SIZE_IN` = 6.0 in; one tag per portrait letter page, 4 pages, 0.5 in quiet zone or more, ruler line as long as the tag). Placement rule: at least 3 readable kit tags per camera (`KIT_MIN_TAGS = 3`; readable = under 55 deg off normal, inside the picture, shortest edge >= 28 px). The recommended tripod spots did not change (A (-78, +65) lens 30 in, B (+65, +78) lens 20 in, 105 deg); only the aim points moved slightly (A: GoPro 340 / +16 / (12, 32, 58), Arducam 343 / +16 / (13, 37, 58); B: 218 / +31 / (13, 37, 60) for both).

| Camera | Before: 4 in tags | After: 6 in tags |
|---|---|---|
| A (`cam0`) | readable 100, 102 (2 of 4); pose from those two: up to 0.86 in / 0.39 deg (GoPro), 1.13 in / 0.73 deg (Arducam) | readable 100, 102, 103 (3 of 4); up to 0.21 in / 0.05 deg (GoPro), 0.12 in / 0.13 deg (Arducam) |
| B (`cam1`) | readable 101, 103 (2 of 4); up to 1.34 in / 0.53 deg (GoPro), 2.85 in / 1.95 deg (Arducam) | readable 101, 102, 103 (3 of 4); up to 0.13 in / 0.07 deg (GoPro), 0.21 in / 0.05 deg (Arducam) |
| All four tags rendered | up to 0.11 in / 0.04 deg | up to 0.11 in / 0.08 deg |

Method: synthetic 1920x1080 frames (tags warped through the virtual camera at the recommended pose, 2 gray levels of noise, 3x3 blur), 8 noise seeds per case, `calib.solve_extrinsics_from_tags`; pose error = camera position distance and rotation angle. Test: `tests/test_tagkit.py::test_each_camera_reads_three_kit_tags_and_solves_accurately[gopro,usb]` (< 0.5 in / 0.3 deg).
Extra tags 104 / 105 (audience-side top bar midpoint -/+ 12 in, derived from `field.hive_frame_wireframe`) were NOT added to the default kit because 6 in tags already give every camera three readable tags; they are available with `extended=True` (`test_optional_bar_tags_add_readable_tags_for_cam1`: with 105, cam1 has four). With 6 in tags + 104/105 the readable counts would be A 3, B 4.
Caveat: the readable tags include far-side kit tags 102 and 103 for both cameras, which can be partly hidden behind the CELL in reality (not modeled).

Tradeoffs and limits (stated in docs/camera_placement.md):
- Only `cam1` reads the CELL tags; `cam0` sees the sticker at 66 deg.
- Each camera reads three of the four 6 in kit tags (A: 100, 102, 103; B: 101, 102, 103).
- Kit tags 17 to 24 px or beyond 60 deg were detected in raw frames but lost in the mp4 test videos, hence the 28 px / 55 deg rule.
- The far-side kit tags can be hidden behind the CELL; this is not modeled.
- Robot box, wall thickness (1.5 in), and every frame dimension are assumptions (VERIFY).

## Outputs

```
$ .venv\Scripts\python.exe -m pytest tests/test_calib.py tests/test_placement.py tests/test_tagkit.py -q
59 passed, 0 failed (the project's addopts "-q" suppresses the summary line)
$ .venv\Scripts\python.exe -m ruff check hiveshot tests
All checks passed!
```

The default map (docs/camera_placement.svg/png) is the Arducam option (the purchased cameras), with the kit tag squares (100-103, dashed 104/105 optional) and the tag reader marked; the GoPro alternative is docs/camera_placement_gopro.svg/png. Both are produced by `placement.write_map(option, ...)`; `test_map_files_exist_and_agree[usb,gopro]` regenerates them from `recommend()` and compares SVG text and PNG pixels.
Not mine: tests/test_setup.py::test_hive_tags_computed_positions_calibrate_without_the_kit assumes both cameras read the up-CELL tags (cam0 sees the sticker at 66 deg here and is not a tag reader), and test_setup_status_reports_tags_seen should expect at least three kit tags per camera ({cam0: 100, 102, 103; cam1: 101, 102, 103}).

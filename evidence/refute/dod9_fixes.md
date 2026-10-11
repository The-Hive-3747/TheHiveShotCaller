# DoD 9 fixes (response to evidence/refute/dod8_9_1.md and dod9_2.md), current state

This file replaces earlier versions. It reflects the CAD-based field (red HIVE at +X, up-CELL opening center (+12.75, 15.77, 59.55), CELL tag row (+12.75, 13.10, 49.79)) and the real CAD HIVE frame (A-frame, see below), the printed tag kit, the constrained placement search and the round-2 refutation (dod9_2.md).

Owned files: hiveshot/calib_targets.py, hiveshot/placement.py, hiveshot/tagkit.py, docs/calibration.md, docs/camera_placement.md/.svg/.png and camera_placement_gopro.svg/.png, tests/test_calib.py, tests/test_placement.py, tests/test_tagkit.py, evidence/refute/dod9_kit_mounting_sim.py/.json. hiveshot/field.py and field_constants.py (single source of geometry) are not edited by this worker.

## Round 2 (dod9_2.md): what was wrong and what changed

| dod9_2 finding | Fix | Evidence |
|---|---|---|
| The kit tags (100-103) and click points 5-8 sat on frame "top corners" at (+-24.73, +-19.475, 63.95) that do not exist: the CAD frame is an A-frame whose highest point is 44.3 in | `calib_targets.frame_top_corners` and `FRAME_TOP_NAMES` are gone. Kit tags use real features from `field.frame_reference_points()`: 100/101 on the audience face of the logo panel at the crossbar ends (x = -12/+12, top edge flush with the panel top at z 40.02; hung from the 1 in crossbar they would sit behind the panel at y 1.55-4.28), 102/103 standing on the tiles at the audience-side base corners (foot bar outer corners (+-24.73, 19.47, 0)) leaning back 20 deg against the foot bar end. 6 in tags | `test_tagkit.py::test_kit_definition`, `test_placement.py::test_frame_is_the_cad_a_frame_and_kit_uses_real_features` |
| Click points 5-8 not physical | The 8 click points are the 8 corners of the red audience up-CELL opening and the blue far up-CELL opening (match-start state); names "Red HIVE up-CELL opening, ..." and "Blue HIVE far-CELL opening, high-left corner" style; `reference_point_names()` is the single source (the UI fetches `GET /api/calib/points`) | `test_calib.py::test_cell_reference_points_equal_field_polygon`, `test_placement.py::test_all_reference_points_inside_both_images`, `test_extrinsics_from_reference_points_at_recommended_poses` |
| Tag 102 overlapped the CELL sticker in cam B | `placement.kit_view` marks a kit tag not readable if its picture quad overlaps the CELL sticker's tag row (6 px gap); none of the recommended readable tags overlaps | `test_frame_is_the_cad_a_frame_and_kit_uses_real_features` |
| In-frame roll check used the nonexistent top bar | Replaced by the line through the centers of tags 100 and 101 (same panel line, 24 in apart): about 10 deg below horizontal going left in cam A, 10 deg above in cam B | docs/camera_placement.md section 2 step 5 |
| Tripod feet never placed (4.5 in out puts a foot on or over the wall) | `TRIPOD_CLEARANCE_IN` 13.5: lens plumb spot 12.0 in from the OUTSIDE face (1.5 in wall); rule stated: one leg pointing straight away from the wall, other feet 10 in toward it for a ~20 in leg radius, so 12 in clears every foot by 2 in; general rule R/2 + 2 in | `test_candidates_outside_wall`, `test_doc_states_tripod_feet_field_size_and_tag_tolerance` |
| Wall numbers vs CAD (inside size 141.35 in, not 144) | The docs say: measure your field wall to wall, the app's `field_size` setting defaults to 144 in (backend adds it), tape numbers are measured from the wall (12.0 in out, along from the corner) so they hold for any size | same test |
| 2 px gate fails for realistic tag taping errors | Study of mounting error (below); docs demand each tag be tape-measured to 0.25 in and tilt to 0.5 deg, and warn that 1.5 to 3 px with good-looking tags means a mis-taped tag | `test_tagkit.py::test_kit_pose_error_vs_tag_mounting_error`, `dod9_kit_mounting_sim.py` |
| calibration.md said the cross-check has no button | Describes the **Cross-check** button on the Calibration tab: out-of-sample by default (tags no solve used), per-point rows, green under 1 in, in-sample fallback with warning, 409/422 meaning | `test_doc_states_tripod_feet_field_size_and_tag_tolerance` |
| Occlusion wireframe and map used the box frame | `placement.occluded` uses `field.hive_frame_wireframe()` (now the A-frame with logo panels); the map draws the A-frame (`_frame_lines`) and the kit tags in top view | `test_map_files_exist_and_agree[usb,gopro]` |

## Kit mounting error study (evidence/refute/dod9_kit_mounting_sim.py, .json)

Synthetic 1920x1080 frames at the recommended poses (noise 2 gray levels, 3x3 blur), each tag displaced by a vector of fixed magnitude (random direction) and tilted by a fixed angle (random axis); the solver uses the model corners. 20 runs per case, two cameras, Arducam option (GoPro within 0.2 in / 0.5 px):

| Tag mounting error | Camera position error median / max | Rotation error median / max | Reprojection shown | Runs under 2 px | CELL opening center error median / max |
|---|---|---|---|---|---|
| exact | 0.14 / 0.21 in | 0.08 / 0.11 deg | 0.8 px | 20/20 | 0.04 / 0.04 in |
| 0.25 in, 0.5 deg | 1.0 / 2.0 in | 0.55 / 1.0 deg | 1.0 px | 20/20 | 0.28 / 0.54 in |
| 0.5 in, 1 deg | 2.1 / 4.1 in | 1.1 / 2.0 deg | 1.7 px | 9/20 | 0.51 / 1.1 in |
| 1 in, 2 deg | 4.2 / 8.0 in | 2.0 / 3.9 deg | 3.2 px | 0/20 | 1.1 / 2.3 in |

(GoPro: 0.25 in: 18/20 under 2 px, 0.5 in: 6/20, 1 in: 0/20.) This confirms the refuter's finding that the 2 px gate only holds with tags placed to about 0.25 in; the kit is therefore defined with tape-measurable positions and the docs require the 0.25 in check.

## Placement constraints (hiveshot/placement.py)

`recommend(option)` searches lens heights 20, 24, 30, 36, 48, 58 in (UBeesize MT60 practical minimum assumed 20 in, VERIFY) on the ring 12 in outside the wall plus every 12 in along the audience wall, jointly for both lens options (one set of tape marks). The nominal aim height is `AIM_Z_IN` = 40 in (the old trajectory-centroid aim at about 60 in put the base tags and the tiles out of the picture, and cost arc coverage), re-centered per camera afterwards. Tiers, compared lexicographically:

1. arc coverage >= 90 % in both and mean triangulation angle 75..120 deg (hard)
2. robot-free rays >= 90 % per camera (hard): robot box 18 x 18 x 24 in + 3 in extension, six sample launch points; targets = ball positions of the first 0.3 s, the up-CELL opening center and the tag row center
3. at least one camera reads the CELL tags (sticker < 55 deg off normal, all four tags inside with 60 px margin, tag edge >= 20 px, tag row ray free of the robot from every launch point): the "tag reader"
4. printed kit readable in both: >= 3 of the 4 six-inch tags (< 55 deg, >= 28 px, inside the picture, not overlapping the CELL sticker)
5. all 8 click points (CELL corners) in view with a 60 px margin
6. not both cameras on the audience wall (allowed only if nothing satisfies 1 to 5)
7. both cameras read the CELL tags (preferred, never traded against 1)

## Result (same positions for GoPro and Arducam)

| | Recommended |
|---|---|
| A (`cam0`) | (-72, +85.5), lens 20 in; outside the audience wall in the -X corner; tag angle 57 deg, not a reader; reads kit tags 100-103 (Arducam, GoPro) |
| B (`cam1`) | (+72, +85.5), lens 20 in; audience wall, +X corner; tag angle 51 deg, **tag reader**; kit tags 100-103 (Arducam), 100, 101, 102 (GoPro) |
| Triangulation | 97 deg (both options) |
| Robot-free rays A / B | 100 % / 98 % (extension 12 in: 98 % / 93 %) |
| Both on the audience wall | yes: no pair with a side-wall camera meets rules 1-5 (a side-wall camera sees the far base tag at 64 deg or more, so cannot read three kit tags). Stated in docs/camera_placement.md rule 6. The corners are used, the drive team stands between them |

Aims (yaw from +X toward +Y / pitch / aim point): A GoPro 327 / +9 / (11, 32, 35), A Arducam 329 / +10 / (12, 35, 38); B GoPro 215 / +11 / (9, 41, 35), B Arducam 218 / +13 / (12, 38, 37). Aim slack at least 4 deg (GoPro B pitch), more elsewhere.
Camera C (optional exit-speed): (+13, +85.5), lens 58 in, 270 deg / -38 deg.
The best "both cameras read the CELL tags" pair does not exist with the 20 px sticker-tag size rule (A sees the sticker 57 deg off normal, 16 to 18 px tag edges), so `both_tags_alternative` equals the recommendation. Earlier results (before the real frame): corner-hung tags at 64 in, A (-78,+65) / B (+65,+78), aim at 60 in, 105 deg.

## Earlier history (round 1, dod8_9_1.md), kept for reference

| # | Finding | Fix | Evidence |
|---|---|---|---|
| 1 | calib_targets used its own CELL geometry that disagreed with field.py | CELL corners read from `field.cell_opening_polygon` | `test_calib.py::test_cell_reference_points_equal_field_polygon` |
| 3 | sheet text said "X toward the audience" | now "+Y toward the audience, X along the red/blue axis" | `test_calib.py::test_point_sheet_axes_match_field_py` |
| 4 | calibration.md was Python calls | app-only procedure; tag-kit method primary, click method fallback; percent-of-image table checked by a test | `test_placement.py::test_calibration_doc_pixel_table_matches_recommend` |
| 5 | camera_placement.md gaps | cam0 = A, cam1 = B, direct PC port per USB camera, yaw/pitch per camera, inside-face convention with 1.5 in wall assumption (VERIFY) | `test_placement.py::test_placement_doc_matches_recommend` |
| 6 | SVG/PNG must equal recommend() | default map = Arducam option with kit tags, A-frame and tag reader marked; GoPro map in camera_placement_gopro.*; both regenerated from `placement.write_map(option, ...)` | `test_map_files_exist_and_agree[usb,gopro]` |

## Tradeoffs and limits (stated in the docs)

- Only `cam1` reads the CELL tags; `cam0` sees the sticker at 57 deg (16 to 18 px tag edges).
- Kit readability is judged by geometry (angle, size, inside the picture, not over the sticker), not by detection on a real field; kit tags below 28 px or beyond 55 deg were lost in the mp4 test videos in earlier synthetic runs.
- The base tags (102, 103) need a small stand and an empty field (a robot would hide them); the mounting tolerance (0.25 in, 0.5 deg) is demanding for a tag leaning on a foot bar end.
- The crossbar tags sit on the logo panel (assumed flat, 5.95 in tall, x +-15.07); a 6 in tag overhangs its bottom edge by 0.05 in.
- Robot box, wall thickness (1.5 in), tripod leg radius (20 in at 20 in lens height) and the MT60's 20 in minimum lens height are assumptions (VERIFY). Positions are exact only for a 144 in field; tape numbers are measured from the wall.
- Not mine, from the refuter: PURCHASE_LIST.md / operator_guide.md staleness (backend worker), `tests/ui_stub_server.py` still lists the old points (UI worker).

## Outputs

```
$ .venv\Scripts\python.exe -m pytest tests/test_calib.py tests/test_placement.py tests/test_tagkit.py -q
(0 failed; the project's addopts "-q" suppresses the summary line)
$ .venv\Scripts\python.exe -m ruff check hiveshot tests
All checks passed!
```

Map regeneration: `placement.write_map('usb'|'gopro', ...)` into temp dirs equals docs/camera_placement.svg/.png and camera_placement_gopro.svg/.png (`test_map_files_exist_and_agree` compares SVG text and PNG pixels).

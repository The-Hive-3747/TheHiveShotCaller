# STEP CAD extraction (data/cad/field-cad-step.zip)

Result: SUCCESS. `tools/step_extract.py` parses the 35 MB STEP (527,790 entities, 188 products,
1076 assembly usages, every one with an ITEM_DEFINED_TRANSFORMATION) straight from the zip,
composes the NAUO / CONTEXT_DEPENDENT_SHAPE_REPRESENTATION / ITEM_DEFINED_TRANSFORMATION /
AXIS2_PLACEMENT_3D chains from the root `am-5850 BIOBUZZ`, and gets part B-rep vertex extents via the
SHAPE_REPRESENTATION_RELATIONSHIP links. Full raw output: `evidence/m1_field/step_extract_out.txt`
(`python -I tools/step_extract.py --summary` / `--extents`). Length unit is METRE (converted to inches).

## Frame of the CAD
x lateral (across the HIVE pair), **y UP**, z along the beam. Red HIVE at x = -12.75, blue at +12.75
(matches RED_HIVE_X/BLUE_HIVE_X); "Audience" CELLs at z > 0, "Scoring" (far) CELLs at z < 0.
Pivot brackets at y = 43.95, z = 0 (confirms PIVOT_HEIGHT). CAD default state = red audience UP, blue
scoring UP (matches Field Setup Guide 11.1). All rotations are exactly +-30 deg (0.866 / 0.5).
Handedness: (x, up, z) is right-handed, so with audience at +Y and Z up the red HIVE is at **+X**; the
project has red at -X (field_constants). See "Consequences".

## Products found
`am-5853-Red/Blue Hive`, `am-5865-red1/red2/blue1/blue2` (Red/Blue Cell Audience/Scoring),
`am-5866-red/blue Goal Rib` (two per CELL: front and back), `am-5869 Top Skin`, `am-5871 Back Skin`,
`am-5888 Hive Goal Bottom Skin` (one per CELL), `am-5888-{red1,red2,blue1,blue2} Goal April Tag`
(the 17 x 5 in sticker, one per CELL), `Goal Pivot Assembly`, `am-5873 Goal Pivot Bracket`.

## World placements (inches; x, up(y), z-beam; axes in CAD world coords)
Bottom Skin (instance origin = a corner of the skin):
- Red Audience:  origin (-22.821, 47.500, 9.086); x=(1,0,0) y=(0,0.866,-0.5) z=(0,0.5,0.866)
- Red Scoring:   origin (-2.663, 37.856, -7.618); x=(-1,0,0) y=(0,0.866,-0.5) z=(0,-0.5,-0.866)
- Blue Audience: origin (2.679, 37.856, 7.618);  x=(1,0,0) y=(0,0.866,0.5) z=(0,-0.5,0.866)
- Blue Scoring:  origin (22.837, 47.500, -9.086); x=(-1,0,0) y=(0,0.866,0.5) z=(0,0.5,-0.866)
  (local extents of every skin: 20.2 x 7.8 x 11.75 in)

Goal Ribs, Red Audience (UP): front/back at origin (-12.742, 58.756, 2.423) and (-12.742, 64.702, 12.722),
y-axis (0,0.866,-0.5), outer-rib z-axis (0,0.5,0.866) = opening normal (30 deg above horizontal, toward the
audience). Rib local extents x +-10.5, y -14.58..+1.45, z -1.94..+0.06 (2 in thick).
Red Scoring (DOWN) ribs: (-12.742, 43.308, -24.333) and (-12.742, 49.254, -14.034).

Goal Rib world extents (y up): Red Audience (up) 46.10 .. 65.93; Red Scoring (down) **30.653 .. 50.49**.
=> the official lowest point 30.6 (Figure 9-9) is the outer rim of the DOWN CELL; the fan value 25.5 is wrong.

Goal Pivot Bracket origins: (-12.167, 43.95, 0), (-13.242, 43.95, 0) for red; (12.258/13.333, 43.95, 0) blue.

## April tag stickers (17.0 x 5.0 in, 0.01 in thick)
Red Audience (up): origin (-4.242, 50.920, 15.050); x=(-1,0,0) y=(0,-0.5,-0.866) z(normal)=(0,-0.866,0.5);
bbox center (-12.742, 49.666, 12.887); extents x -21.24..-4.24, up 48.41..50.92, z 10.72..15.06.
Normal in the field frame (audience = +Y): (0, +0.5, -0.866) -- faces down and toward the audience.
Red Scoring (down): bbox center (-12.742, 35.647, -11.394). Blue Audience center (12.758, 35.647, 11.394),
Blue Scoring (12.758, 49.666, -12.887).

## Rigid-body check (beam coordinates a along the beam, b perpendicular, from the pivot, audience-up frame)
- Up opening bottom edge center (rib local y = -12.934 from the official 53.5): a = 21.45, b = -1.33
  => opening plane at |a| = CELL_PAIR_SPAN/2 = 21.455, b_bottom = -1.37 (model).
- Sticker bbox center: Red Audience (a,b) = (14.019, -1.493); Red Scoring (-14.019, -1.493). The far CELL is
  the near CELL with a -> -a and b unchanged (rotation by 180 deg about b_hat), exactly as modeled.
- Sticker ref-hole line is the sticker's bottom edge, a = 11.52 = 21.455 - 9.938 (official 9.938) so the tag
  row center is at a = 14.267, 7.188 behind the opening, 0.25 beyond the sticker center (as modeled).
- Model tag row center (red audience-up): (-12.75 +- offsets, y = 13.10, z = 49.79). CAD sticker center
  (y = 12.887, z = 49.666) + 0.25 along the beam gives (13.10, 49.79). Match within 0.01 in.

## Consequences
1. The up CELL opening center is at y = **15.77** (not 24.25): the opening plane is at 21.455 along the
   beam, and the old y came from an unofficial fan-site heuristic. z unchanged (59.55). The tag row is
   at y = 13.10, z = 49.79 (not the 21.54 / 49.9 in docs/research_apriltags.md, which used the 27.76
   bottom-edge value derived from the same fan numbers).
2. Down CELL (rigid body): opening center z = 38.09, bottom-edge z = 32.03; outer rim 30.61 vs official 30.6.
3. Red/blue mirror: CAD says red at +X for a right-handed frame with audience at +Y (or red at -X with
   audience at -Y). Either flip RED_HIVE_X/BLUE_HIVE_X or move the audience to -Y. Tag ids ascend toward image-right
   of the sticker; id order along X for the red audience cell is -X in a right-handed frame with audience +Y.
4. Assumptions in the extractor: geometry representation shares the local frame of its parent
   SHAPE_REPRESENTATION (checked: sticker local extents are 17 x 5 x 0.01 as published); vertices only
   (no curve sampling), so extents are those of B-rep vertices.

# HIVE frame and field perimeter (CAD, added after the DoD 9 refutation)
Command: `.venv/Scripts/python.exe -I tools/step_extract.py --frame --perimeter`; raw output
`evidence/m1_field/step_frame_out.txt` (includes the per-part min/max and SVD centerline endpoints).
CAD axes here (x lateral, y = field Y with audience at +, z up in the table below are FIELD axes: the CAD's
y-up and z-beam were relabeled to field z-up and field y; the frame is symmetric in X and Y).

**The frame is not a box and not 49.46 in at the apexes.** Product `am-5854: Frame` = two leaning A-frames,
one at each X end, with a 24 in crossbar between the apexes.

| Feature (CAD part) | Field-frame vertices (inches) |
|---|---|
| Foot bar, 4 outer corners on the tiles (`am-5878 Sheet Metal Foot Bar`, x 22.75..24.73, 2.15 high) | (+-24.73, +-19.47, 0) |
| Foot bar inner corners | (+-22.75, +-19.47, 0); bar top at z = 2.15 |
| Leg foot ends, centerline (`am-5876 A-Frame Leg`, 4x) | (+-23.81, +-18.56, 0.53) |
| Leg apex ends, centerline | (+-12.60, +-0.52, 41.05) |
| Crossbar (`am-5875 A-Frame Top Bar`, 24 in long, 1.0 x 1.0 in) | from (-12.0, 0, 41.45) to (+12.0, 0, 41.45) (bar spans z 40.95..41.95) |
| Pivot cradle (`am-5863 Axle Holder`) | (+-12.0, 0, 44.27) top, (+-11.15, 0, 41.57) bottom; max z 44.31 |
| Top corner block (`am-5874`) | x 10.51..13.76, z 39.49..44.21 (each side) |
| Logo panel (`am-5877 ACM Panel` + `am-5883 Panel Sticker`, both faces) | x +-15.07, z 34.07..40.02, y = +-1.55 .. +-4.29 |
| Under-tile bars (`am-5880`, 47.5 in CC) | x +-23.89, y = +-16.53, z -0.74..-0.63 |

Apex heights: crossbar 41.45 (top 41.95), pivot cradle 44.31, tallest frame point 44.31. The manual's
49.46 x 38.95 are the foot-bar footprint (CAD 49.46 x 38.94). The old "top corners" at (+-24.73, +-19.475,
63.95) do not exist.

## Field perimeter
| CAD item | extent |
|---|---|
| Side glass inner face | |x|, |y| = 70.674 (glass 70.674..70.792) -> **inside size 141.35 in** |
| Soft tiles | +-70.585 -> 141.17 in |
| Perimeter rails / panels / links (outer) | +-71.65 -> 143.30 in; panel inner flanges from 67.16 |
Manual nominal "approximately 144 in" (+-72) is about 2.65 in larger than the CAD inside faces.
Constants added: `FIELD_INSIDE_SIZE_CAD = 141.35`, `FIELD_TILE_SPAN_CAD = 141.17`,
`FIELD_PERIMETER_OUTER_CAD = 143.30` (FIELD_SIZE stays 144.0).

# Logo panel (tilted plate) and flowers (CAD; `tools/step_extract.py --panel`, raw: step_panel_out.txt)
The logo panel (`am-5877 ACM Panel` + `am-5883 Panel Sticker`) is a thin plate (ACM 0.12 in + 0.01 in sticker)
LEANING 24.00 deg from vertical with the legs, one per Y side (the earlier vertical-at-y=4.28 model was wrong).
Plane fit of the audience panel: center (x, y, z) = (-0.03, 2.96, 37.11), outward normal (0, 0.9135, 0.4067).

Outer (sticker) face corners, audience (+Y) panel, field frame inches (far panel = Y mirror):

| Corner | x | y | z |
|---|---|---|---|
| bottom, +X | +14.58 | 4.292 | 34.125 |
| bottom, -X | -14.58 | 4.292 | 34.125 |
| top, -X | -13.22 | 1.666 | 40.024 |
| top, +X | +13.22 | 1.666 | 40.024 |
Slant height 6.46 in (centerline); the bottom corners also carry ~0.5 in tabs out to x = +-15.07 at z = 34.69,
and the top corners are chamfered (x 13.2..13.7). Order in `field.logo_panel_face` is counter-clockwise about the normal
(bottom-left, bottom-right, top-right, top-left seen from outside).

Flowers (`am-5855: Flower Assembly` x4): footprint 5.88 x 5.01 in (layers B/C/X), height to z = 22.65
(backstop top), stems (HIPS pipes) z 4.25..21.25, brackets run to the wall (|coord| 71.79). Centers (field frame,
CAD x -> -x, CAD z -> y): (23.393, -68.136), (-23.393, 68.136), (68.136, 23.393), (-68.136, -23.393); long side along the wall.
The arrangement is point-symmetric, not mirror-symmetric. Cylinder radius used: 3.86 (circumscribed circle of the footprint).

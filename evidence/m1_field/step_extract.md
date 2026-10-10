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

# Research note: the field's own AprilTags (official sources, 2026-10-10)

Sources read directly: Competition Manual TU04 Section 9 (text and Figures 9-8, 9-9, 9-10, 9-11, 9-15, 9-16, 9-17), Initial Field Element Assembly Guide V1.0 (steps 6.1, 6.3, 6.9, 6.10), Event Field Setup Guide (section 12 HIVE calibration, 11.1 start state), FIRST AprilTag Clusters tech tip. Field CAD (STEP v26-27.2) downloaded for follow-up.

## Facts
- Sticker: four 3.25 in 36h11 tags on one sticker; tag centers at ±2.75 and ±6.5 in from the cluster center; tag centerline 2.75 in above the reference-hole line; reference holes 0.5 in dia, 7.0 in either side of the cluster centerline (Figure 9-15).
- Placement: sticker on the exterior of the clear Hive Bottom Skin (the CELL floor, the 20 in base of the gabled Goal Rib), aligned by the reference holes, holes 9.938 in from the front (opening) of the CELL, so the tag row is 7.19 in behind the opening edge; sticker bottom edge toward the field center; "facing downward towards the TILES" (Figures 9-15, 9-16; Assembly Guide 6.1/6.3).
- Ids (Figure 9-17 text, partly garbled in extraction; confirmed by the printable art and multiple teams): red far 30-33, red audience 34-37, blue audience 38-41, blue far 42-45; stickers are labeled RED/BLUE AUDIENCE/SCORING.
- HIVE: pivot 43.95 in; 30° settled tilt; up opening 53.5-65.6 in; lowest point of the down CELL 30.6 in; CELLs 12.04 in deep, 18.84 in apart, 42.91 in outer span; HIVEs 25.5 in apart; CELL cross-section 20 in wide, 7.61 in shoulder, 14 in peak (Figures 9-8 to 9-11).
- Match start (Field Setup Guide 11.1): red HIVE audience CELL up, blue HIVE scoring (far) CELL up, 3 NECTAR in each up CELL.
- Tags move with the HIVE; the SDK reports the up CELL cluster with roll within ±90° and the down CELL outside; it is not a fixed landmark.

## Derived and then CAD-confirmed (up CELL, audience-up state, red)
- The official STEP CAD (tools/step_extract.py, evidence/m1_field/step_extract.md) places the opening plane 21.455 in along the beam from the pivot: up opening center (x_h, 15.77, 59.55), edges 53.49/65.61; down opening 32.03-44.15; lowest rim 30.61 (official 30.6).
- Tag row center: (x_h, 13.10, 49.79) matched to the CAD sticker center within 0.01 in; tags at x_h + {+6.5, +2.75, -2.75, -6.5} for ids ascending (ids ascend toward -X as seen from the audience side, i.e. left to right from the audience; VERIFY on the real field).
- Red is on the audience's left (Manual 9.5), which in this right-handed frame (Z up, audience +Y) is +X: RED_HIVE_X = +12.75.
- The earlier hand derivation (y=21.54) assumed the fan-site opening position y=24.25 and is superseded.
- Sticker normal: (0, +0.5, -0.866): faces down and toward the audience. In the far-up state the mirror applies (faces the far side).
- The down CELL is now pinned by the CAD (rigid beam model reproduces the official 30.6 in lowest point to 0.01 in), so both CELLs' tags are computable; learning remains as a verification step.

## Consequences for the design
1. Calibration: the kit (two tags on the slanted logo panel, two standing at the audience-side base corners of the frame; docs/calibration.md) stays the default for accuracy; the up CELL's four known tags give a no-printer fallback and a continuous check.
2. HIVE state: read automatically from which clusters are visible right-side-up (roll within ±90°) with hysteresis; tips logged automatically; no manual toggling once cameras see the tags.
3. Camera placement: from (−78, 65, 36) and (65, 78, 36) the up CELL sticker is seen about 65° off its normal (marginal). Lower (18-24 in) and closer to the audience wall gives about 50°. placement.recommend() gets a tag-visibility term; the placement map and docs are regenerated from it.

## Sources
- https://ftc-resources.firstinspires.org/ftc/game/manual-09 (Section 9 PDF)
- https://ftc-resources.firstinspires.org/ftc/field/initialfieldguide
- https://ftc-resources.firstinspires.org/ftc/field/eventfieldguide
- https://ftc-resources.firstinspires.org/ftc/field/apriltag-art (production art), /ftc/field/field-cad-step (STEP)
- https://ftc-docs.firstinspires.org/en/latest/tech_tips/tech-tips/tech-tip-apriltag-clusters/tech-tip-apriltag-clusters.html

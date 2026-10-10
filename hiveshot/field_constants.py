"""BIOBUZZ field and HIVE constants. Inches unless noted.

Field frame: origin at field center on the tile surface. Z up. X positive
toward the audience side. Y positive along the HIVE beam toward the "far"
(non-audience... see note) end. The beam runs along Y; the red and blue
HIVEs are offset from each other along X.

Sources: Competition Manual sections 9.2, 9.6, 9.8 (via fan transcriptions:
littlepotatorobotics biobuzz-field simulator, Evanston09/ftc-biobuzz-sim,
Raptoria25068/hive-shot-planner). Marked VERIFY where the official CAD has
not been checked. All values editable in settings; these are defaults.
"""

FIELD_SIZE = 144.0                   # inside wall to inside wall
TILE_SIZE = 24.0

# HIVE structure (one frame at field center carrying two HIVEs)
FRAME_WIDTH_X = 49.46                # VERIFY
FRAME_DEPTH_Y = 38.95                # VERIFY
PIVOT_HEIGHT = 43.95
HIVE_CENTER_SPACING_X = 25.5         # red <-> blue, along X. VERIFY
RED_HIVE_X = -HIVE_CENTER_SPACING_X / 2
BLUE_HIVE_X = +HIVE_CENTER_SPACING_X / 2

# Per-HIVE beam with a CELL at each end
BEAM_HALF_LENGTH = 15.44             # pivot to CELL center along Y. VERIFY
CELL_GAP = 18.84                     # inner gap between the two CELLs
CELL_EXTENT_Y = 12.04                # CELL depth along beam

# CELL opening (in its own plane)
CELL_OPENING_WIDTH = 20.0            # along X
CELL_OPENING_HEIGHT = 14.0           # in-plane height
CELL_TILT_DEG = 30.0                 # beam tilt when settled (bi-stable)
OPENING_PLANE_FROM_HORIZONTAL_DEG = 59.87
OPENING_NORMAL_ABOVE_HORIZONTAL_DEG = 30.13
UP_CELL_OPENING_CENTER_Z = 59.55     # settled state
DOWN_CELL_OPENING_CENTER_Z = 31.55
UP_CELL_OPENING_Z_RANGE = (53.5, 65.6)
DOWN_CELL_OPENING_Z_RANGE = (25.5, 37.6)
GABLE_SHOULDER_HEIGHT = 7.61

# Scoring elements
POLLEN_DIAMETER = 2.8
POLLEN_MASS_G = 25.0                 # AndyMark am-5851 0.055 lb
NECTAR_DIAMETER = 3.6
NECTAR_MASS_G = 41.0                 # AndyMark am-5852 0.091 lb
POLLEN_COUNT = 40
NECTAR_COUNT = 16

# AprilTags on CELL bottoms
APRILTAG_FAMILY = "36h11"
APRILTAG_SIZE = 3.25
APRILTAG_IDS = {                     # VERIFY against Figure 9-17
    ("red", "far"): (30, 31, 32, 33),
    ("red", "audience"): (34, 35, 36, 37),
    ("blue", "audience"): (38, 39, 40, 41),
    ("blue", "far"): (42, 43, 44, 45),
}

# Physics
GRAVITY_IPS2 = 386.09                # 9.80665 m/s^2 in in/s^2
AIR_DENSITY_KG_M3 = 1.204
DRAG_CD_DEFAULT = 0.55

# Robot (defaults; owner to confirm, QUESTIONS.md #4)
ROBOT_LENGTH = 18.0
ROBOT_WIDTH = 18.0
ROBOT_HEIGHT = 18.0
ROBOT_LAUNCH_EXIT_HEIGHT = 12.0
MAX_BALLS_HELD = 4

# HIVE AprilTag clusters (research 2026-10-10; see docs/research_apriltags.md)
# Four 3.25 in tags per CELL in a horizontal row on the CELL underside, facing the
# tiles, lower edge toward field center. Row offsets along the row (inches), left
# to right as the ids ascend. The row's position relative to the CELL is NOT
# published in a trustworthy form; the app LEARNS tag poses per settled state
# (hiveshot.tagkit.learn_hive_tags) instead of assuming them.
HIVE_TAG_ROW_OFFSETS_IN = (-6.5, -2.75, 2.75, 6.5)
HIVE_TAG_CLUSTERS = {               # cluster name -> ids left to right
    "red_far": (30, 31, 32, 33),
    "red_audience": (34, 35, 36, 37),
    "blue_audience": (38, 39, 40, 41),
    "blue_far": (42, 43, 44, 45),
}
HIVE_TAG_ROW_HEIGHT_UP_IN = 50.2     # one team's measurement, VERIFY by learning
HIVE_TAG_ROW_HEIGHT_DOWN_IN = 35.0   # one team's measurement, VERIFY by learning

# ---- Official numbers read from the Competition Manual TU04 Section 9 figures and the
# ---- Initial Field Element Assembly Guide V1.0 on 2026-10-10 (docs/research_apriltags.md)
HIVE_LOWEST_POINT_Z = 30.6          # Figure 9-9: "Bottom of HIVE above TILES"
UP_CELL_OPENING_TOP_Z = 65.6        # Figure 9-9
UP_CELL_OPENING_BOTTOM_Z = 53.5     # Figure 9-9
CELL_DEPTH = 12.04                  # Figure 9-10 (same as CELL_EXTENT_Y)
CELL_PAIR_SPAN = 42.91              # Figure 9-10 outer-to-outer
CELL_CROSS_SECTION = {              # Figure 9-11 Goal Rib: pentagon, base at the floor (Bottom Skin)
    "width": 20.0, "shoulder_height": 7.61, "peak_height": 14.0,
}
# AprilTag sticker (Figure 9-15), on the exterior of the Hive Bottom Skin (CELL floor),
# bottom edge of the sticker toward the field center (Figure 9-16, Assembly Guide 6.1/6.3).
TAG_STICKER_REF_HOLE_FROM_FRONT = 9.938   # reference-hole centerline from the front of the CELL
TAG_ROW_ABOVE_REF_HOLES = 2.75            # tag centerline is 2.75 in toward the front from the holes
TAG_ROW_FROM_CELL_FRONT = TAG_STICKER_REF_HOLE_FROM_FRONT - TAG_ROW_ABOVE_REF_HOLES  # 7.188 in
TAG_REF_HOLE_HALF_SPACING = 7.0           # holes are 7.0 in either side of the cluster centerline
TAG_REF_HOLE_DIAMETER = 0.5
# Derived for the UP cell (audience-up, red): floor runs from the opening bottom edge
# (y=27.76, z=53.5) into the cup along (0, -cos30, -sin30); tag row center at
# y = 27.76 - 7.188*cos30 = 21.54, z = 53.5 - 7.188*sin30 = 49.9 (a team measured 50.2).
# Sticker exterior normal (0, +sin30, -cos30): faces the tiles and the audience side.

"""Wedge (4 wide x 2 deep x 5.5 tall, right triangle in y-z) under a 7 x 7 in card at tag 103 (+X base corner):
overlap with the foot bar end (x 22.75..24.73, y <= 19.47, z <= 2.15) and the leg foot (capsule r 0.5 from (23.81,18.56,0.53)),
for three lateral wedge placements; plus statics of the card on its wedge. Run: PYTHONPATH=. .venv/Scripts/python.exe evidence/refute/dod9_5/wedge_fit.py"""
import math
import numpy as np
from hiveshot import tagkit
t20 = math.tan(math.radians(20))
yb = 19.47 + 2.15 * t20                      # card bottom on the tile
print("card bottom y", round(yb, 4), " wedge slope 2/5.5 =", round(2 / 5.5, 5), " tan20 =", round(t20, 5), " angle", round(math.degrees(math.atan(2 / 5.5)), 3), "deg; slope face length", round(math.hypot(2, 5.5), 3), "in; card 7 in")
rng = np.random.default_rng(0)
def overlap(x0, x1, n=400000):
    p = np.c_[rng.uniform(x0, x1, n), rng.uniform(yb - 2, yb, n), rng.uniform(0, 5.5, n)]
    inw = p[:, 1] <= yb - p[:, 2] * 2 / 5.5
    bar = (p[:, 0] >= 22.75) & (p[:, 0] <= 24.73) & (p[:, 1] <= 19.47) & (p[:, 2] <= 2.15)
    a, b = np.array([23.81, 18.56, 0.53]), np.array([12.6, 0.52, 41.05])
    ab = b - a; tt = np.clip(((p - a) @ ab) / (ab @ ab), 0, 1); leg = np.linalg.norm(p - (a + tt[:, None] * ab), axis=1) <= 0.5
    vol = (x1 - x0) * 2 * 5.5
    return (inw & bar).mean() * vol, (inw & leg).mean() * vol, inw.mean() * vol
for label, (x0, x1) in {"inboard (x 18.73..22.75, tagkit.py comment)": (18.73, 22.75),
                       "centered on the black square (x 19.73..23.73)": (19.73, 23.73),
                       "centered on the 7 in card (x 19.73..23.73 same)": (19.73, 23.73),
                       "outboard flush with bar outer face (x 20.73..24.73)": (20.73, 24.73)}.items():
    b, l, v = overlap(x0, x1)
    print(f"wedge {label}: wedge volume {v:.1f} in3, overlap with foot bar {b:.2f} in3, with leg foot {l:.2f} in3")
# statics: card (7x7, 0.19 thick ignored) bottom edge at yb, leaning back 20 deg; CoM
c_y = yb - 3.5 * math.sin(math.radians(20)); c_z = 3.5 * math.cos(math.radians(20))
print("card CoM y,z:", round(c_y, 3), round(c_z, 3), " wedge base y range", yb - 2, "..", yb, "-> CoM inside the wedge base footprint:", yb - 2 <= c_y <= yb)
print("card top z (7 in along slope):", round(7 * math.cos(math.radians(20)), 2), " wedge top z 5.5 -> card overhangs the wedge by", round(7 - math.hypot(2, 5.5), 2), "in of slope length")
# tag corners as modeled
for i in (102, 103):
    print(i, tagkit.tag_corners_xyz(i).round(3).tolist())

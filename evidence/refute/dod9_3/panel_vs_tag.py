import numpy as np
from hiveshot import tagkit, field
from hiveshot import field_constants as fc
# real panel plane (audience +Y face), from CAD verts (field frame): top edge (y=1.657,z=40.02), bottom edge (y=4.283,z=34.121) (face with sticker)
top = np.array([1.666, 40.024]); bot = np.array([4.292, 34.125])   # sticker (outer) surface
t = (top-bot)/np.linalg.norm(top-bot)     # up along slant (dy,dz)
slant = np.linalg.norm(top-bot)
tilt = np.degrees(np.arctan2(bot[0]-top[0], top[1]-bot[1]))
n = np.array([ t[1], -t[0]])  # normal (dy,dz) pointing +y?
if n[0] < 0: n = -n
print("panel slant height %.3f in, tilt from vertical %.2f deg, normal (y,z)=%s" % (slant, tilt, n.round(3)))
for tid in (100, 101):
    c = tagkit.tag_corners_xyz(tid)
    print("tag", tid, "model corners (x,y,z):"); print(c.round(3))
    # distance of each model corner to the real panel plane (signed along n)
    d = [(p[1]-top[0])*n[0] + (p[2]-top[1])*n[1] for p in c]
    print(" distance of model corners from real panel face (in, + = in front of panel):", np.round(d,2))
    cen = c.mean(0)
    print(" center dist %.2f in; model normal %s vs panel normal (0,%.3f,%.3f): angle %.1f deg" % (
        (cen[1]-top[0])*n[0]+(cen[2]-top[1])*n[1], tagkit.tag_normal_xyz(tid).round(3), n[0], n[1],
        np.degrees(np.arccos(np.dot(tagkit.tag_normal_xyz(tid), [0,n[0],n[1]])))))
# Where would a tag taped flat on the panel (top edge flush with panel top edge, 6 in, centered x=+-12) have its corners?
def real_corners(sx, size=6.0):
    h = size/2
    u = np.array([0.0, -t[0]*-1, 0])  # placeholder
    up = np.array([0.0, t[0], t[1]])   # slant-up direction in (x,y,z)
    nn = np.array([0.0, n[0], n[1]])
    r = np.cross(up, nn)
    # top-edge midpoint
    topmid = np.array([sx*12.0, top[0], top[1]])
    c = topmid - h*up
    return np.array([c + h*up - h*r, c + h*up + h*r, c - h*up + h*r, c - h*up - h*r]), nn
for tid, sx in ((100,-1),(101,1)):
    rc, nn = real_corners(sx)
    mc = tagkit.tag_corners_xyz(tid)
    print("tag", tid, "REAL flat-on-panel corners:"); print(rc.round(2))
    print(" per-corner offset vs model (in):", np.linalg.norm(rc-mc,axis=1).round(2), " center offset %.2f (dy %.2f dz %.2f)" % (np.linalg.norm(rc.mean(0)-mc.mean(0)), rc.mean(0)[1]-mc.mean(0)[1], rc.mean(0)[2]-mc.mean(0)[2]))
# panel outline in x vs slant depth, from the CAD: vertices (x, y, z) for + side
V = np.array([[-13.226,1.657,40.02],[-13.712,1.811,39.674],[-15.072,4.031,34.688],[-14.587,4.283,34.121],[14.572,4.283,34.121],[15.058,4.031,34.688],[13.697,1.811,39.674],[13.212,1.657,40.02]])
print("Panel outline (sticker face) x,y,z:"); print(V)
# half width at top edge flat = 13.2, so tag corner at x=15 at top is outside
print("tag 101 spans x 9..15; panel top flat edge only reaches x=%.2f; corner chamfer to x=%.2f at z=%.2f" % (13.212, 13.697, 39.674))
# overhang of the tag's upper outer corner beyond panel outline (linear interp of panel side edge x(z)): side edge from (13.697,39.674) to (15.058,34.688)
def panel_halfwidth(z):
    if z>=40.02: return 0
    if z>=39.674: return 13.212+(13.697-13.212)*(40.02-z)/(40.02-39.674)
    if z>=34.688: return 13.697+(15.058-13.697)*(39.674-z)/(39.674-34.688)
    return 15.058-(15.058-14.572)*(34.688-z)/(34.688-34.121)
for z in (40.0,39.0,38.0,37.0,36.0,35.0,34.2):
    print(" z=%.1f: panel half-width %.2f, tag outer edge x=15.0 -> overhang %.2f in" % (z, panel_halfwidth(z), 15.0-panel_halfwidth(z)))

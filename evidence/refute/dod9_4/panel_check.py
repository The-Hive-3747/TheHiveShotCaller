import numpy as np, math
from hiveshot import field, tagkit
from hiveshot import field_constants as fc
quad, n = field.logo_panel_face("audience")
print("quad"); print(np.round(np.array(quad),3)); print("n", np.round(n,4))
exp = np.array([[14.58,4.292,34.125],[-14.58,4.292,34.125],[-13.22,1.666,40.024],[13.22,1.666,40.024]])
print("quad vs STEP max abs diff", np.abs(np.array(quad)-exp).max())
en = np.array([0,0.9135,0.4067]); print("normal diff", np.abs(np.array(n)-en).max(), "norm", np.linalg.norm(n))
q=np.array(quad,float); nn=np.array(n,float)
# planarity
print("planarity", [float((p-q[0])@nn) for p in q])
# tags
for t in tagkit.KIT_TAGS:
    c = tagkit.tag_corners_xyz(t.id) if hasattr(tagkit,'tag_corners_xyz') else None
    print(t.id, t.kind)
    c=np.array(c)
    if t.kind=="panel":
        d=(c-q[0])@nn
        print(" dist to plane per corner", np.round(d,5))
        # inside trapezoid: param along slant
        bottom=0.5*(q[0]+q[1]); top=0.5*(q[2]+q[3]); u=(top-bottom)/np.linalg.norm(top-bottom)
        slant=np.linalg.norm(top-bottom)
        for p in c:
            s=(p-bottom)@u  # along slope
            hw = 14.58 + (13.22-14.58)*s/slant
            print("   corner x=%.3f s=%.3f/%.3f halfwidth_at_s=%.3f  margin_x=%.3f margin_top=%.3f margin_bot=%.3f"%(p[0],s,slant,hw,hw-abs(p[0]),slant-s,s))
    else:
        print(np.round(c,3))
        # base: bottom edge on tile z=0? touches foot bar end
        print(" bottom corners z", c[2][2], c[3][2], " y", c[2][1])
        print(" tag plane y at z=2.15:", None)
        nrm=np.cross(c[1]-c[0], c[3]-c[0]); nrm/=np.linalg.norm(nrm); print(" normal", np.round(nrm,3))
        # y on face plane at z = FRAME_BASE_HEIGHT
        base=c[2]; 
        # plane through bottom edge with normal n
        for z in (2.15,):
            y = base[1] - (z-base[2])*nrm[2]/nrm[1]
            print(" face plane y at z=%.2f: %.3f (foot bar end y=19.47)"%(z,y))
print("frame ref points"); 
for k,v in field.frame_reference_points(): print(k,v)
print("FRAME_BASE_HEIGHT", fc.FRAME_BASE_HEIGHT)

import numpy as np
from hiveshot import placement as pl, field
pts = pl._stack(pl.sample_trajectories())
print("n pts", len(pts))
rec = {o: pl.recommend(o) for o in ("usb","gopro")}
old_a = np.array([-72,85.5,20.0])
print("flowers", [(f["xy"], f["radius"], f["z_range"]) for f in field.flower_positions()])
print("old A (-72,85.5,20) flower:", pl.flower_blocked(old_a, pts).mean())
for o,r in rec.items():
    pa=np.array(r["cameras"]["A"]["pos"],float); pb=np.array(r["cameras"]["B"]["pos"],float)
    for k,p in (("A",pa),("B",pb)):
        fb=pl.flower_blocked(p,pts).mean(); fr=pl.occluded(p,pts).mean()
        print(o,k,"flower %.4f frame %.4f union %.4f"%(fb,fr,(pl.flower_blocked(p,pts)|pl.occluded(p,pts)).mean()))
    # via score_pair (the occluded_frac the doc uses)
    sc=r["pair_score"]; print(o,"pair occluded_frac",sc["occluded_frac"],"frac_in_both",sc["frac_in_both"],"mean angle",sc["mean_angle_deg"])
# independent box FLOWER test for A, B and old A
def seg_box(p0,p1,lo,hi):
    d=p1-p0; tmin,tmax=0.0,1.0
    for i in range(3):
        if abs(d[i])<1e-12:
            if p0[i]<lo[i] or p0[i]>hi[i]: return False
        else:
            t1,t2=(lo[i]-p0[i])/d[i],(hi[i]-p0[i])/d[i]
            if t1>t2:t1,t2=t2,t1
            tmin,tmax=max(tmin,t1),min(tmax,t2)
            if tmin>tmax:return False
    return True
# CAD footprint 5.88 (along wall) x 5.01 (normal) centered at flower centres
bx=[]
for f in field.flower_positions():
    cx,cy=f["xy"]
    if abs(cy)>abs(cx): hx,hy=5.88/2,5.01/2   # on y wall: long side along x
    else: hx,hy=5.01/2,5.88/2
    bx.append((np.array([cx-hx,cy-hy,0.0]),np.array([cx+hx,cy+hy,22.65])))
for name,p in (("oldA",old_a),("A",np.array(rec["usb"]["cameras"]["A"]["pos"],float)),("B",np.array(rec["usb"]["cameras"]["B"]["pos"],float))):
    fr=np.mean([any(seg_box(p,q,lo,hi) for lo,hi in bx) for q in pts]); print("box",name,round(fr,4))

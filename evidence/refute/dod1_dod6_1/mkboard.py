import sys, numpy as np, cv2
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker")
from hiveshot import calib_targets as ct
img,page=ct.render_checkerboard()
H,W=img.shape; DPI=300; bw,bh=10,7
x0=(W-bw*DPI)/2; y0=(H-0.5*DPI-bh*DPI)/2
# strip caption text: keep as-is (it's part of the printed page)
K=np.array([[900,0,960],[0,900,540],[0,0,1.]])
S=np.array([[1/DPI,0,-x0/DPI],[0,1/DPI,-y0/DPI],[0,0,1.]])
rng=np.random.default_rng(int(sys.argv[2]))
out=sys.argv[1]
vw=cv2.VideoWriter(out, cv2.VideoWriter_fourcc(*'mp4v'), 60.0, (1920,1080))
n=0
for p in range(40):
    while True:
        # board center at (5, 3.5) in board coords; choose rotation about center
        rx,ry,rz=rng.uniform(-35,35),rng.uniform(-35,35),rng.uniform(-20,20)
        R,_=cv2.Rodrigues(np.radians([rx,ry,rz]).astype(np.float64))
        depth=rng.uniform(22,38)
        cx,cy=rng.uniform(-14,14)*depth/38*1.0, rng.uniform(-8,8)*depth/38
        c=np.array([5.0,3.5,0.0])
        t=np.array([cx,cy,depth])-R@c
        M=K@np.column_stack([R[:,0],R[:,1],t])@S
        # check that board corners lie inside image
        corners=np.array([[0,0,1],[10,0,1],[10,7,1],[0,7,1]],float).T
        pr=K@np.column_stack([R[:,0],R[:,1],t])@corners; pr=(pr[:2]/pr[2]).T
        if (pr[:,0]>20).all() and (pr[:,0]<1900).all() and (pr[:,1]>20).all() and (pr[:,1]<1060).all(): break
    fr=cv2.warpPerspective(img,M,(1920,1080),flags=cv2.INTER_AREA,borderValue=90)
    fr=cv2.cvtColor(fr,cv2.COLOR_GRAY2BGR)
    for _ in range(30):
        vw.write(fr); n+=1
vw.release(); print(out,n,'frames')

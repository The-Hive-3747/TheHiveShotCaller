import sys, numpy as np
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker")
from hiveshot import calib, placement as pl, calib_targets as ct
ref=ct.field_reference_points()
for name,pos in (('A',(-78,65,36)),('B',(65,78,36))):
    for hf in (86,):
        I,E=pl.camera_from_pose(pos,(-13,41,61),hf,1920,1080,name)
        uv=calib.project(I,E,np.array([p for _,p in ref]))
        print(name,'hfov',hf)
        for (n,p),q in zip(ref,uv): print('   %-48s %s  %8.1f %8.1f %s'%(n,tuple(round(x,1) for x in p),q[0],q[1],'' if (0<=q[0]<1920 and 0<=q[1]<1080) else 'OUT OF FRAME'))

# the 8-point list as it was at 15:32-15:38 (old calib_targets.field_reference_points), recreated from the code I read
import sys, numpy as np
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker")
from hiveshot import calib, placement as pl, field_constants as fc
fx,fy=fc.FRAME_WIDTH_X/2, fc.FRAME_DEPTH_Y/2
old=[("HIVE frame base corner (-X, -Y)",(-fx,-fy,0.0)),("HIVE frame base corner (+X, +Y)",(fx,fy,0.0)),
     ("Tile intersection (-48, -48)",(-48.,-48.,0.)),("Tile intersection (+48, +48)",(48.,48.,0.))]
for name,pos in (('A',(-78,65,36)),('B',(65,78,36))):
    I,E=pl.camera_from_pose(pos,(-13,41,61),86,1920,1080,name)
    uv=calib.project(I,E,np.array([p for _,p in old]))
    print(name)
    for (n,p),q in zip(old,uv): print('   %-36s %8.1f %8.1f %s'%(n,q[0],q[1],'' if (0<=q[0]<1920 and 0<=q[1]<1080) else 'OUT OF FRAME'))

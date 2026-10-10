import json, sys
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker")
from hiveshot import calib
from hiveshot.models import CameraIntrinsics, CameraExtrinsics
I=[];E=[]
for c in ("cam0","cam1"):
    t=json.load(open(rf"C:\Users\3747h\Documents\HiveShotTracker\fixtures\synth_basic\{c}_truth.json"))
    i=t["intrinsics"]; e=t["extrinsics"]
    I.append(CameraIntrinsics(**i)); E.append(CameraExtrinsics(**e))
calib.save_calibration(sys.argv[1], I, E)
print("saved", sys.argv[1])

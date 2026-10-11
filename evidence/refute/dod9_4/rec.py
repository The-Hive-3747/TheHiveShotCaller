import json, numpy as np
from hiveshot import placement as pl
for opt in ("usb","gopro"):
    r = pl.recommend(opt)
    print("=====", opt)
    def clean(o):
        if isinstance(o, dict): return {k: clean(v) for k,v in o.items() if k not in ("trajectories",)}
        if isinstance(o, (list,tuple)): return [clean(v) for v in o]
        if isinstance(o, np.ndarray): return np.round(o,3).tolist()
        if isinstance(o, (np.floating,float)): return round(float(o),3)
        return o
    print(json.dumps(clean(r), indent=1, default=str)[:6000])

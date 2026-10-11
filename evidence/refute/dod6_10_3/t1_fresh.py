import json, sys
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker\evidence\refute\dod6_10_3")
from hs3 import Api
api = Api(8796)
cfg = api.ok("GET", "/api/config")
out = {}
def snap(label):
    st = api.ok("GET", "/api/pipeline/status")
    c = api.ok("GET", "/api/calib")
    out[label] = dict(calibration_loaded=st["calibration_loaded"], calibration_source=st["calibration_source"],
        intrinsics_default=st["intrinsics_default"], warnings=st["warnings"],
        cams={k:(v.get("calibration_source"), v.get("intrinsics_source")) for k,v in st["cameras"].items()},
        calib_intr_n=len(c.get("intrinsics",[])), calib_extr_n=len(c.get("extrinsics",[])), calib_fx=[i["fx"] for i in c.get("intrinsics",[])])
snap("default_fixture")
for kind, tgt0, tgt1 in (("device", 0, 1), ("rtmp", "cam0", "cam1")):
    m = json.loads(json.dumps(cfg))
    m["sources"] = [dict(cam_id=f"cam{i}", kind=kind, target=t, width=1920, height=1080, fps_hint=60, backend="auto", loop=False, realtime=True) for i,t in enumerate((tgt0, tgt1))]
    code, new, _ = api.call("PUT", "/api/config", m)
    out[f"put_{kind}"] = code
    snap(f"sources_{kind}")
    # UI rule: wizard opens when sources_configured false or calibration_loaded false
    out[f"sources_{kind}"]["wizard_opens"] = (len(new["sources"]) < 2) or (not out[f"sources_{kind}"]["calibration_loaded"])
print(json.dumps(out, indent=1))

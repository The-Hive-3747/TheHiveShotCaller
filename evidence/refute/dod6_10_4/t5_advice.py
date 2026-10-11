import sys, json, time
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker\evidence\refute\dod6_10_4")
import rig4 as G
from rig4 import *
port = int(sys.argv[1]); model = sys.argv[2]
api = S.Api(port)
base = SCR / f"learn_{model}" / "vid"
out = {}
for nm in ("aud", "mstart", "far"):
    paths = {c: str(base / f"{nm}_{c}.mp4") for c in ("cam0", "cam1")}
    set_sources(api, srcs(paths)); time.sleep(3)
    rows = []
    for i in range(4):
        c, d, _ = api.call("GET", "/api/setup/status")
        rows.append(dict(tags=d.get("tags_seen"), roll=d.get("tags_roll"), tip=[r for r in d.get("recommendations", []) if "Tip both" in r]))
        time.sleep(1.2)
    out[nm] = rows
    print(nm)
    for r in rows: print("  ", r["tags"], json.dumps(r["roll"]), r["tip"])
json.dump(out, open(HERE / f"t5_advice_{model}.json", "w"), indent=1)

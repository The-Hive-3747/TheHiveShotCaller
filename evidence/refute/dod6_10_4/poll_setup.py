import sys, json, time
sys.path.insert(0, r"C:\Users\3747h\Documents\HiveShotTracker\evidence\refute\dod6_10_2")
import simlib as S
api = S.Api(int(sys.argv[1]))
for i in range(int(sys.argv[2])):
    c, d, _ = api.call("GET", "/api/setup/status")
    print(c, d.get("tags_seen"), json.dumps(d.get("tags_roll")), d.get("recommendations"))
    time.sleep(1.5)

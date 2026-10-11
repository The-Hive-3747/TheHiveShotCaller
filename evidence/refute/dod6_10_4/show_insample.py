import json, sys
d=json.load(open(sys.argv[1]))
print("tags", d.get("tags_drawn"))
print("baseline finish", json.dumps(d["0_baseline_finish"],default=str)[:700]); print("baseline acc", d["0_baseline_acc"]["pos_err_in"], d["0_baseline_acc"]["traj_p95"], d["0_baseline_acc"]["cell_center_err"])
print("baseline xc", d["0_baseline_crosscheck"])
for n,e in d.get("gates",{}).items():
    r=e["res"]
    print("\n==",n,"auto_all code",e["code"],"ok",r.get("ok"),"rolled_back",r.get("rolled_back"),"changed",e["changed"],"max",r.get("max_error_in"))
    for c,v in r["per_cam"].items(): print("   ",c,{k:v[k] for k in ("ok","status","error","oos_error_in","reprojection_px","warnings") if v.get(k) is not None})
    print("   warnings",r.get("warnings"))
    print("   acc",e["acc"].get("pos_err_in") if "pos_err_in" in e["acc"] else e["acc"], "p95",e["acc"].get("traj_p95"),"cell",e["acc"].get("cell_center_err"))
    print("   status warns",e["status"]["warnings"],"mismatch",e["status"]["mismatch"])
    f=e["finish"]; print("   FINISH",f["code"],"ok",f.get("ok"),"oos",f.get("out_of_sample"),"per-cam",f.get("oos_error_in_per_camera"),"max",f.get("max_error_in"),"ack_needed",f.get("ui_needs_ack"),"\n      warnings",f.get("warnings"),"\n      detail",f.get("detail"))
    print("   XC",e["crosscheck"])
    print("   restore",e.get("restore",{}).get("ok"),e.get("restore",{}).get("acc",{}).get("pos_err_in"))
w=d.get("swap")
if w:
    print("\n== swap status",w["status"]["warnings"],w["status"]["mismatch"]); print("  xc",w["crosscheck"]); print("  finish",json.dumps(w["finish"],default=str)[:900]); print("  auto_all",json.dumps(w["auto_all_swapped"],default=str)[:1500]); print("  finish_after",json.dumps(w["finish_after_resolve"],default=str)[:500])

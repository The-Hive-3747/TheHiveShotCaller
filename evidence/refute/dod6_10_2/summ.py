import json,glob,sys
def g(d,*ks):
    for k in ks:
        if d is None: return None
        d=d.get(k) if isinstance(d,dict) else None
    return d
for f in sorted(glob.glob("results_*.json")):
    r=json.load(open(f)); s=r["steps"]; n=r["scenario"]
    a=s.get("accuracy",{}) or {}
    aa=s.get("2_auto_all") or s.get("3b_click") or {}
    print("==",n,"truth_fx",round(r.get("truth_fx",0),1),"drawn",r.get("tags_drawn"))
    if "per_cam" in aa:
        for c,v in aa["per_cam"].items():
            print("  ",c,{k:(round(x,3) if isinstance(x,float) else x) for k,x in v.items() if k in("ok","rmse_in","tags_used","reprojection_px","max_corner_px","warnings","error","code","max_err_px","n_over_2px","detail")})
    cc=aa.get("crosscheck"); print("   crosscheck(auto/click):",cc, "| after:",s.get("crosscheck_after"),"| in_sample:",s.get("crosscheck_in_sample"), "| src",r.get("src_latest_mtime"))
    if "error" in a: print("   ACC", a); 
    else:
        print("   pose:", {c:(round(v["pos_err_in"],2),round(v["rot_err_deg"],2),round(v["fx_app"]),round(v["fx_true"])) for c,v in (a.get("cams") or {}).items()})
        print("   traj err mean/p95/max in:", [round(a['trajectory'][k],2) for k in("mean_in","p95_in","max_in")] if a.get("trajectory") else None,
              " cell_center_err", round(a.get("cell_opening_center_err_in",-1),2))
    f5=s.get("5_finish",{}); print("   finish: loaded",f5.get("calibration_loaded"),"src",f5.get("hive_state_source"),"warn",f5.get("warnings"),"mismatch",f5.get("calibration_mismatch"))
    ln=s.get("3_learn");
    if ln: print("   learn:", {k:(v.get("code"),v.get("up_cell_error_in"),v.get("detail","")[:60] if v.get("detail") else "") for k,v in ln.items() if isinstance(v,dict)})
    if "2_intrinsics_doc" in s: print("   intr:",{k:v for k,v in s["2_intrinsics_doc"].items() if k!="note"})

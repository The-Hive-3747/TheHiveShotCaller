import json, numpy as np
for opt in ("usb","gopro"):
    d=json.load(open(f"evidence/refute/dod9_2/sim_{opt}.json"))
    print("=====",opt)
    for cn,rs in d.items():
        print("--",cn)
        for vn in ("kit","kit+hive","hive","click8","click_cell4","click_cell_red+bluefar"):
            ok=0; reproj_ok=0; tot=0; maxpt=0; both_ok=0
            for r in rs:
                v=r[vn]; 
                cs=v["cams"]
                rp=[c.get("reproj_px",c.get("reproj_rmse_px")) for c in cs if "fail" not in c]
                reprojpass = len(rp)==2 and all(x<2 for x in rp)
                trip = "tri" in v and v["tri"]["opening_center"]<1
                reproj_ok+=reprojpass; ok+=trip; both_ok+= (reprojpass and trip); tot+=1
            print(f"  {vn:24s} reproj<2px both cams {reproj_ok}/{tot}; opening-center err<1in {ok}/{tot}; both criteria {both_ok}/{tot}")
        # per-point <2px for click8
        pp=[ (c["max_px"]<2) for r in rs for c in r["click8"]["cams"]]
        print("  click8: cam-runs with max per-point error < 2 px:", sum(pp),"/",len(pp))
        print("  kit-only max_px<2 across cam-runs:", sum(c["max_px"]<2 for r in rs for c in r["kit"]["cams"] if "max_px" in c), "/", sum(1 for r in rs for c in r["kit"]["cams"] if "max_px" in c))
        # the hive outlier
        for r in rs:
            for k,c in enumerate(r["hive"]["cams"]):
                if "pos_err_in" in c and c["pos_err_in"]>20: print("  hive-only gross outlier: seed",r["seed"],"cam",k,c)

import json, collections
for opt in ("usb","gopro"):
    d=json.load(open(f"evidence/refute/dod9_2/sim_{opt}.json"))["mount0"]
    for v in ("click8","click_cell4","click_cell_red+bluefar"):
        print(opt, v, [collections.Counter(r[v]["cams"][k]["n_in_image"] for r in d) for k in (0,1)])

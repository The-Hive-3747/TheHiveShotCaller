import hashlib, pathlib
from hiveshot import placement as p, kit_figure as kf
out = pathlib.Path("evidence/refute/dod9_5/regen"); out.mkdir(exist_ok=True)
p.write_map('usb', out/'camera_placement.svg', out/'camera_placement.png')
p.write_map('gopro', out/'camera_placement_gopro.svg', out/'camera_placement_gopro.png')
kf.write_kit_figure(out/'kit_tag_positions.png', out/'kit_tag_positions.svg')
for n in ['camera_placement.svg','camera_placement.png','camera_placement_gopro.svg','camera_placement_gopro.png','kit_tag_positions.svg','kit_tag_positions.png']:
    a=(out/n).read_bytes(); b=pathlib.Path('docs/'+n).read_bytes()
    print(n, hashlib.sha256(a).hexdigest()[:16], hashlib.sha256(b).hexdigest()[:16], "IDENTICAL" if a==b else "DIFFERENT", len(a), len(b))

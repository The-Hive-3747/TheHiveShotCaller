import hashlib, pathlib
from hiveshot import placement as p
out = pathlib.Path("evidence/refute/dod9_4/regen")
p.write_map('usb', out/'camera_placement.svg', out/'camera_placement.png')
p.write_map('gopro', out/'camera_placement_gopro.svg', out/'camera_placement_gopro.png')
for n in ['camera_placement.svg','camera_placement.png','camera_placement_gopro.svg','camera_placement_gopro.png']:
    a=(out/n).read_bytes(); b=pathlib.Path('docs/'+n).read_bytes()
    print(n, hashlib.sha256(a).hexdigest()[:16], hashlib.sha256(b).hexdigest()[:16], "IDENTICAL" if a==b else "DIFFERENT", len(a), len(b))

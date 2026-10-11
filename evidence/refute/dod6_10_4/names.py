import re, sys
from pathlib import Path
R = Path(r"C:\Users\3747h\Documents\HiveShotTracker")
ui = (R/"ui/index.html").read_text(encoding="utf-8") + "\n" + (R/"ui/app.js").read_text(encoding="utf-8")
uil = ui.lower()
for doc in ("docs/calibration.md", "docs/operator_guide.md"):
    txt = (R/doc).read_text(encoding="utf-8")
    toks = []
    for m in re.finditer(r"\*\*([^*\n]{2,80})\*\*", txt):
        toks.append(m.group(1).strip(" .,:;"))
    seen = set(); out = []
    for t in toks:
        if t in seen: continue
        seen.add(t)
        # strip numbering like "1. " for steps
        base = re.sub(r"^\d+\.\s*", "", t)
        found = (t.lower() in uil) or (base.lower() in uil)
        out.append((t, found))
    print("==", doc, len(out))
    for t, f in out:
        print(("OK   " if f else "MISS ") + t)

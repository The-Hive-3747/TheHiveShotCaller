# PyInstaller one-folder build. Run via build.ps1 (pyinstaller hiveshot.spec).
import os
import sys

from PyInstaller.utils.hooks import collect_submodules

hidden = (
    collect_submodules("hiveshot")
    + collect_submodules("uvicorn")
    + collect_submodules("websockets")
    + collect_submodules("scipy.special")
    + ["httptools", "anyio._backends._asyncio", "multipart"]
)

# --- VC++ 2015-2022 runtime, shipped app-local so a PC without the redistributable can start the exe.
# PyInstaller 6 places `binaries` destined for "." in <bundle>/_internal (the exe's DLL search dir).
# Search order: the Python install the venv was built from (python.org installers ship vcruntime140*.dll
# but not msvcp140.dll), then C:\Windows\System32. A missing required DLL stops the build.
_VC_REQUIRED = ["msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll"]
_VC_OPTIONAL = ["concrt140.dll"]
_vc_dirs = []
for _d in (getattr(sys, "base_prefix", None), sys.prefix,
           os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")):
    if _d and os.path.isdir(_d) and _d not in _vc_dirs:
        _vc_dirs.append(_d)


def _find_vc(name):
    for d in _vc_dirs:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return None


vc_binaries = []
_missing = []
for _n in _VC_REQUIRED + _VC_OPTIONAL:
    _p = _find_vc(_n)
    if _p:
        vc_binaries.append((_p, "."))
    elif _n in _VC_REQUIRED:
        _missing.append(_n)
if _missing:
    raise SystemExit(
        "hiveshot.spec: cannot bundle the VC++ runtime; not found: " + ", ".join(_missing)
        + ". Searched: " + "; ".join(_vc_dirs)
        + ". Install the Microsoft Visual C++ Redistributable (x64) on the build PC and rebuild.")
print("hiveshot.spec: bundling VC++ runtime ->", ", ".join(os.path.basename(p) for p, _ in vc_binaries))

# Demo/fixture videos. synth_basic is required; synth_20 (demo mode prefers it) is bundled when present.
_fixture_datas = [("fixtures/synth_basic", "fixtures/synth_basic")]
if os.path.isdir(os.path.join(SPECPATH, "fixtures", "synth_20")):
    _fixture_datas.append(("fixtures/synth_20", "fixtures/synth_20"))
    print("hiveshot.spec: bundling fixtures/synth_20")
else:
    print("hiveshot.spec: fixtures/synth_20 not found; demo will use synth_basic")

a = Analysis(
    ["build/entry.py"],
    pathex=["."],
    binaries=vc_binaries,
    datas=[
        ("ui", "ui"),
        ("bin", "bin"),
    ] + _fixture_datas,
    hiddenimports=hidden,
    excludes=["tkinter", "matplotlib", "pytest", "ruff", "IPython"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="HiveShotTracker", console=True)
coll = COLLECT(exe, a.binaries, a.datas, name="HiveShotTracker")

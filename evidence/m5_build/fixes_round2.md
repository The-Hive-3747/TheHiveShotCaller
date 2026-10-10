# M5 build fixes, round 2 (response to evidence/refute/dod8_9_1.md, DoD 8 section)

Owner: build worker. Full build.ps1 was NOT run (lead will). Only a spec-only PyInstaller run into a temp dir, plus one run of the existing smoke test against the OLD dist.

## Mapping
| # | Refutation finding | Fix | Where |
|---|---|---|---|
| 1 | No plain msvcp140.dll in the bundle; only VCRUNTIME140(_1) | `binaries` now includes msvcp140.dll, vcruntime140.dll, vcruntime140_1.dll (required) and concrt140.dll (optional), destination ".", i.e. `_internal\` in PyInstaller 6.22.3. Source search: `sys.base_prefix` (the Python install the venv derives from), `sys.prefix`, then `%SystemRoot%\System32`. Spec aborts with a clear `SystemExit` message if a required DLL is not found. (No hardcoded user path.) | hiveshot.spec; test `test_vc_runtime_dlls_ship_with_bundle` (3 params, case-insensitive lookup in bundle root and `_internal`) |
| 2 | Zip ships no docs | build.ps1 copies all of `docs\*` to `dist\HiveShotTracker\docs\` (12 files, incl. camera_placement.md/.png/.svg, camera_bracket.md/.stl/.png, guides, clean_machine_test.md) and writes `README.txt` (CRLF, UTF-8 no BOM) at the folder root next to the exe: how to run, data location, docs list, SmartScreen note. Both happen before Compress-Archive. | build.ps1; test `test_bundle_ships_docs_and_readme` |
| 3 | Exit code 3 on stop | Smoke test now stops the exe with CTRL_BREAK (new process group), falls back to terminate then kill, accepts exit codes {0, 1, 3}, records the actual code and stop method with `record_property` and a printed line. Operator guide and troubleshooting say closing the console is the normal way to stop and 0/1/3 are normal. | tests/test_build_smoke.py, docs/operator_guide.md section 1, docs/troubleshooting.md |
| 4 | No real clean-machine test | docs/clean_machine_test.md checklist (requirements, steps A-G, results table, sign-off). DoD 8 explicitly marked "NOT YET MET; requires owner to run this checklist". | docs/clean_machine_test.md |
| 5 | Operator guide accuracy | Checked every label against ui/index.html and ui/app.js; corrected (see below). Added Node/Python-free install and default data folder `%LOCALAPPDATA%\HiveShotTracker\data`. | docs/operator_guide.md |

### Operator guide corrections (vs ui/index.html + ui/app.js)
- "Save" -> **Save config**; "restart the pipeline" -> **Pipeline stop** then **Pipeline start**.
- Settings: described real layout (Sources rows: cam_id, kind, target, width, height, fps_hint, realtime, loop; Add source / remove / use picked device; Match; Robot; Detector).
- "Shots list" -> **Shots** tab; counters are the Dashboard tiles (Shots, Made, Bounce-out, Miss, Make rate, Tips, mean exit m/s, in/s, launch angle).
- Equation and fit RMSE are shown in the **Replay** info box, not on the dashboard; equation format `z = a s^2 + b s + c (in)` (physics.equation_string), not "x".
- Failure chart: title "Failures by burst order", x labels "burst 1..4, burst >4", red = all failures, amber = bounce-outs (legend text "All failures / Bounce-outs").
- Shots table columns: #, Time, Burst, Ball, Result, Exit m/s, Exit in/s, Angle, Azimuth, Apex in; Result filter all/made/miss/bounce_out.
- Replay: speed is a drop-down (0.1, 0.25, 0.5, 1 x), not buttons; Play toggles to Pause; added Follow ball checkbox, scrub slider, clip link; opened by clicking a Shots row.
- Export: **Export CSV** link in the top bar (needs a session selected in the Session drop-down).
- Calibration tab buttons documented (Refresh image, Undo point, Clear, Solve extrinsics, Start/Stop intrinsics, Current calibration box); "calibration mismatch (n)" tag explained from pipeline.calibration_mismatch (image size mismatch).
- Data location: removed the wrong "`_internal\data`" default; default is `%LOCALAPPDATA%\HiveShotTracker\data` (config.default_data_dir, frozen). Reworded Option B USB to "own USB 3 port if you can" consistent with troubleshooting "Low fps" (the owner's no-hub decision is in SHOPPING_LIST/PURCHASE_LIST; camera_placement.md still says hub and is not mine).
- troubleshooting.md: mediamtx path `_internal\bin\mediamtx.exe`; Detector section name; SmartScreen/antivirus note; missing-DLL entry; exit-code note; data location; hub wording.

## Verification actually done
1. `PyInstaller hiveshot.spec --noconfirm --distpath <scratch>\specdist --workpath <scratch>\specwork` (PyInstaller 6.22.3): exit 0. Log: evidence/m5_build/spec_verify_round2.log (line "hiveshot.spec: bundling VC++ runtime -> msvcp140.dll, vcruntime140.dll, vcruntime140_1.dll, concrt140.dll"). Result listing of `specdist\HiveShotTracker\_internal`: concrt140.dll, msvcp140.dll, vcruntime140.dll, vcruntime140_1.dll all present, one copy each (no duplicate/case clash with the DLLs PyInstaller already collected). msvcp140.dll and concrt140.dll came from System32 (the python.org install has vcruntime140*.dll only).
2. Import scan with pefile of the OLD dist (before this change): numpy `_multiarray_umath` and `_pocketfft_umath` import `msvcp140-a4c2229bdc2a2a630acdc095b4d86008.dll` (the delvewheel-hashed copy, which IS shipped in numpy.libs), plus vcruntime140.dll / vcruntime140_1.dll. No .pyd/.dll in the bundle imports plain `msvcp140.dll`, `msvcp140_1`, `concrt140` or `vcomp140`. So the refuter's point 2 (numpy needs a plain msvcp140.dll) is not borne out by the import tables; the plain DLLs are shipped anyway as defense in depth and for any future dependency.
3. build.ps1: PowerShell parser reports 0 errors. The new docs/README block was executed in isolation against a scratch folder: produced `docs\` with 12 files and `README.txt` (1766 bytes, no bare LF, content as intended). The full script was not run.
4. tests/test_build_smoke.py: `ruff check` passes. Ran against the OLD dist (built before this change): `test_packaged_exe_runs_from_foreign_cwd` PASSED with `stop_method=ctrl_break exit_code=3`; `test_vc_runtime_dlls_ship_with_bundle[msvcp140.dll]` and `test_bundle_ships_docs_and_readme` FAILED as expected on the old dist (they correctly detect the gaps); vcruntime140.dll and vcruntime140_1.dll params passed. These two must be re-run against the new build after the lead runs build.ps1.

## Not verified / limits
- New dist from build.ps1 not produced by me; the zip contents (docs, README.txt, DLLs) are unverified until the lead's build and `pytest tests/test_build_smoke.py`.
- DoD 8 remains NOT MET: only the owner's run of docs/clean_machine_test.md on a real clean PC/VM can meet it. Nothing here establishes behavior without the VC++ redistributable.
- build.ps1 cannot be run as a file under this machine's execution policy (scripts disabled); the lead should run it the way they normally do (not changed here).
- `Compress-Archive` in Windows PowerShell 5.1 may write backslash entry names; unchanged behavior, noted for the clean-machine test (Windows Explorer unzip is fine).
- Other refutation items outside my files (camera_placement.md hub vs direct-USB, cam0/cam1 mapping, calibration.md Python-API prose, CELL geometry mismatch) are untouched.

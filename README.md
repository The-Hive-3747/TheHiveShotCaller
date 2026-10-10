# TheHiveShotCaller (HiveShotTracker)

Camera-based shot analytics for the FTC BIOBUZZ (2026-27) HIVE. Two USB cameras watch the HIVE; the app detects every ball launched, decides made / miss / bounce-out, computes exit speed, launch angle and the fitted trajectory, tracks which ball in a burst fails, and replays each shot in a 3D view of the field, HIVE and robot.

## Quick start (no hardware)

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]
powershell -ExecutionPolicy Bypass -File tools\fetch_deps.ps1   # MediaMTX binary + official PDFs
.venv\Scripts\python -m hiveshot.app --demo
```

Open http://127.0.0.1:8765. Demo mode runs from bundled synthetic videos with nothing connected. The packaged release (`build.ps1` → `dist/HiveShotTracker_<version>_win64.zip`) runs the same way with `HiveShotTracker.exe --demo`.

## With cameras

See `docs/operator_guide.md` (setup wizard, calibration with the printed AprilTag kit or the HIVE's own tags, sessions, export) and `docs/camera_placement.md` (tripod positions, map in `docs/camera_placement.png`). Hardware list: `PURCHASE_LIST.md`. Printable camera bracket: `docs/camera_bracket.stl`.

## Project documents

- `PLAN.md` — goals, milestones, Definition of Done, refuter process
- `QUESTIONS.md` — questions parked for the owner
- `HANDOFF.md` — current state for the next session
- `docs/api.md` — HTTP/WebSocket contract between backend and UI
- `docs/research_apriltags.md` — field geometry from the official manual and STEP CAD
- `evidence/` — test output, reviews and refuter reports per milestone

## Tests

```powershell
.\test.ps1
```

Runs ruff and pytest (about 250 tests on synthetic fixtures; live-hardware tests need `HIVESHOT_LIVE=1`). The UI's JavaScript is syntax-checked with Node when available.

## Stack

Python 3.12, OpenCV (contrib) 5, NumPy, SciPy, FastAPI, SQLite; browser UI with vendored three.js; MediaMTX for wireless RTMP ingest; PyInstaller for the Windows build.

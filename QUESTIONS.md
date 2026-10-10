# Questions parked for owner review

Answer inline. Each item states the assumption I proceeded with so nothing is blocked.

| # | Date | Question | Assumption used | Owner answer |
|---|---|---|---|---|
| 1 | 2026-10-10 | Approve downloading Three.js (about 700 KB, jsDelivr CDN) to vendor into the UI? | Load from CDN at runtime until approved. | Approved 2026-10-10; vendored three 0.170.0 in ui/vendor. Owner also pre-approved all software downloads needed. |
| 2 | 2026-10-10 | Approve downloading MediaMTX (about 20 MB, GitHub releases) for wireless RTMP ingest? | RTMP mode implemented against the MediaMTX interface but untested until the binary is present. | Approved; mediamtx v1.21.2 in bin/. |
| 3 | 2026-10-10 | Camera option A (GoPro) or B (USB global shutter)? Software supports both; the placement map is drawn for both. | Build and test with generic video sources plus the laptop webcam; final placement numbers assume 60 in tripods. | |
| 4 | 2026-10-10 | Robot box dimensions for the 3D viewer (length, width, height, launcher exit height)? | 18 x 18 x 18 in box, launcher exit at 12 in, editable in settings. | |
| 5 | 2026-10-10 | DoD 8 clean-machine smoke test (owner action): run docs/clean_machine_test.md on a separate PC or fresh VM as a non-admin user with no Python and no VC++ redistributable, copying only the release zip; use a real USB camera and an RTMP publisher (GoPro Quik or ffmpeg); record the results table and the zip SHA256. | Reported as NOT MET until then; same-machine stripped-environment runs do not count. | |
| 6 | 2026-10-10 | Which camera is which: the placement map names cam A = cam0 (minus-X wall) and cam B = cam1 (plus-Y wall). OK, or do you want a different convention? | cam0 = A, cam1 = B. | |
| 7 | 2026-10-10 | HIVE AprilTags: RESOLVED from the official manual figures and assembly guide (docs/research_apriltags.md, docs/official/). Only the down CELL's floor position remains unpinned; the app learns it or extracts it from the STEP CAD. No owner action needed. | Up-CELL tags computed; down-CELL learned. | resolved |

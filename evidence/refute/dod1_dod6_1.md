# Refuter report dod1_dod6_1 (DoD 1 and DoD 6)

Date: 2026-10-10, 15:28 to 15:50 MDT. Refuter: independent agent, read-only on source. Raw outputs: `evidence/refute/dod1_*.txt`, `evidence/refute/dod6_*.txt`; scripts and the generated checkerboard PDF: `evidence/refute/dod1_dod6_1/`.

IMPORTANT: the source tree changed while I tested (other workers editing). Timestamps of what I tested:
- Until 15:39 the 8 field points were 4 CELL corners plus 4 floor points (frame base corners, tile intersections), and `docs/calibration.md` was Python-only.
- 15:39:23 `hiveshot/calib_targets.py` changed to 4 CELL corners + 4 HIVE frame-top corners. 15:42 `hiveshot/app.py` gained `/api/calib/checkerboard.pdf` and `/api/calib/points`. 15:42:54 `docs/calibration.md` was rewritten for the UI.
- `ui/app.js` (last modified 15:41:48) was NOT updated: it still hardcodes the old 8 names. Source was quiet (no edits for 60 s) at 15:47, and my final verdicts are for that state.
- `dist\HiveShotTracker` (built 15:30) predates all of these changes.

## DoD 1: "starts with one command ... two cameras over both a capture card/USB device and RTMP, switchable in settings"

**Verdict: NOT REFUTED** on the running code and on the packaged exe, with several real weaknesses (below). The "switchable in settings" part is the weakest: it works only if the operator knows to type a full URL as the RTMP target.

What I did and saw (all with fresh temp data dirs, ports 8770/8771, webcam device 0, port 1935):

(a) One command. `.\run.ps1 --port 8770 --data-dir <tmp>` started uvicorn; `GET /api/config` answered after about 5 s. Also started `dist\HiveShotTracker\HiveShotTracker.exe --port 8770 --data-dir <tmp>`: same. OK.

(b) Device path (`dod1_b_device.txt`). PUT sources `[cam0 device 0 640x480 fps_hint 30, cam1 file synth loop]`; start; 11 s of polling. cam0: is_alive true, fps 29.7 to 31.7, frames_read 8 to 312, last_error null, reconnects 0. cam1 about 60 fps. PUT of `sources` while running returned 409 ("sources cannot be changed while the pipeline is running; stop it first"); PUT of `burst_gap_s` while running returned 200; stop 0.4 s. The same device path worked in the packaged exe (cam0 135 frames in 5 s at 30.2 fps).

(c) RTMP path (`dod1_c*.txt`, `dod1_x_packaged_exe.txt`).
- Source with kind rtmp and target `cam0` / `cam1` (the bare names the brief suggested): the pipeline starts, `rtmp.running` true and the urls are listed (`rtmp://127.0.0.1:1935/cam0`), but the cameras never connect: `last_error: "cannot open rtmp source 'cam0' ..."`, 0 frames, forever. The target is passed unchanged to OpenCV, so it must be the full URL. This is a usability trap, not a crash (see weakness W1).
- Target `rtmp://127.0.0.1:1935/cam0` and `.../cam1` with the exact ffmpeg publish commands from the brief: with no publisher the cameras retry (open fails, last_error set, no crash, mediamtx stays up). About 8 s after publishing started cam0 read frames at 60 fps, cam1 about 14 s after (backoff). Both is_alive true, frames_read increasing (about 1000 per cam per 20 s), fps 60.
- With a calibration.json in the data dir (copied from the fixture truth), the RTMP run detected 33 shots in 65 s (made/miss mixed, exit speed about 5.5 to 6.1 m/s). Without a calibration.json the RTMP cameras ran but 0 shots were produced and nothing in the status or UI said why (W5).
- Packaged exe: rtmp.running true, mediamtx.exe started from the bundle, both cams 60 fps, 2184 and 2513 frames in about 45 s.

(d) Switching while stopped (`dod1_e_break.txt`). PUT sources device, rtmp, files, device; each time stop, PUT, start, 5 s: every combination started and produced frames (rtmp: expected 0 frames with no publisher). Config persisted across an app restart (sources, sessions: 56 shots survived).

(e) Break attempts:
- PUT sources while running: 409. OK.
- Bad device index 7: start returns 200, cam0 shows `last_error "cannot open device source 7 ..."`, retries, no crash; cam1 unaffected. Named device 'abc': same (DSHOW). Missing file: camera ended, error shown.
- `kind: "banana"`: PUT accepted (200) and persisted; start returned 500 `'banana' is not a valid SourceKind`, no crash, pipeline not running (W3). Duplicate cam_id: accepted, silently collapses to one camera.
- Zero sources: PUT 200, start 200 (running with nothing).
- Stop/start x3 with RTMP, double start, double stop: all 200; stop took 0.02 s; after every stop `tasklist` showed no mediamtx/ffmpeg/hiveshot process (`dod1_e_break.txt`).
- Hard kill (taskkill /F of the app while the RTMP pipeline ran): mediamtx.exe was orphaned and kept port 1935. A restarted app then ran the pipeline fine against the orphan, but status showed `rtmp.running: false` while RTMP worked (W6). Closing the console window should kill both (shared console) and I did not test that; only the forced-kill case is shown.

Processes I started: all killed (run.ps1 instances, the exe, mediamtx 15600 orphan, ffmpeg publishers). Final `netstat` shows nothing listening on 8770, 8771, 1935. The other python.exe processes in `tasklist` are not mine (they existed before or belong to parallel agents).

### DoD 1 weaknesses
- W1 (medium): RTMP target must be the full URL. Operator guide says "set `kind` to `rtmp`" and "status page lists the exact URLs" but never says to paste that URL into `target`, and the Settings form does not prefill it. Typing the stream name (`cam0`) gives a camera that is "alive" with 0 frames forever. The Settings UI does not show the URLs at all (they exist only in `/api/pipeline/status` JSON; `grep` of ui/ finds no "urls" use).
- W2 (low-medium): stopping the pipeline stops mediamtx, so any publisher (the GoPro) is dropped and must reconnect itself; restart delivered frames only after about 8 to 14 s. Camera `is_alive` is true while `frames_read` is 0 and last_error is set, so a dead RTMP camera looks alive.
- W3 (low): invalid `kind` and duplicate `cam_id` are accepted by PUT /api/config and persisted; only the start fails (500). The Settings select box prevents the bad kind in the UI.
- W4 (low-medium): first `GET /api/devices` after app start returned `[]` (device probe times out at 1 s; log "device probe 0 timed out"); the second call listed the webcam. Reproduced in both source and exe. The Settings device picker can show nothing on first open.
- W5 (medium): no calibration present means zero shots with no visible reason, for RTMP/device sources (the fixture-truth fallback only works for `file` sources).
- W6 (low): orphan mediamtx after a forced kill; `rtmp.running` reports false when the new mediamtx failed to bind but the old one serves.
- MediaMTX listens on 0.0.0.0:1935 (needed for the GoPros, but note for the firewall guidance).
- Not tested (no hardware): capture card, a real GoPro, 240 fps, two USB cameras at once.

## DoD 6: "Calibration can be redone by the operator in under 10 minutes following the guide"

**Verdict: REFUTED** on the current code. Reproduction (UI path, the only path an operator of the packaged exe has):

1. `run.ps1 --port 8771 --data-dir <fresh>`; PUT sources to two file sources (checkerboard videos I rendered with `mkboard.py`, 1080p); Pipeline start.
2. Intrinsics via the API (equivalent to the Calibration tab buttons): cam0 RMSE 0.180 px, 39 frames; cam1 0.227 px, 39 frames; 20 s record each, 1.5 s solve each.
3. Open the Calibration tab, click 8 points on the cam0 card in the order shown, click **Solve extrinsics**.
4. Result: toast `POST /api/calib/extrinsics/cam0: 422 {"detail":"unknown reference point name 'HIVE frame base corner (-X, -Y)'"}` and no solve (`dod6_g_ui_solve_toast.txt`, `dod6_e_current_code_extrinsics.txt`). The card lists 4 floor points (frame base corners, tile intersections) because `CALIB_POINTS` is hardcoded in `ui/app.js` lines 7 to 16, while `/api/calib/points` and the guide now use 4 frame-top corners. An operator cannot complete the extrinsics step at all. Cause: the UI list was not updated when `calib_targets.field_reference_points()` changed; the UI should fetch `/api/calib/points`.

Before 15:39 the same flow was refuted for a second reason (still relevant history): 4 of the 8 old points (floor points) project outside a 1920x1080 frame from the guide's own recommended camera spots (`dod6_c2_old_point_visibility.txt`: e.g. cam A base corner at v=1543, tile (+48,+48) at v=1288; cam B (+48,+48) at u=-234, v=3096). The new list fixes that: all 8 points are in frame for both cameras (`dod6_c_point_visibility.txt`; cam B point 8 at u=80, near the edge).

What works (API flow with the new point list, `dod6_f_latest_flow.txt`, clean data dir): checkerboard PDF served (200, application/pdf, MediaBox 792x612 = letter landscape); `/api/calib/points` returns 8 names; intrinsics as above; extrinsics from 8 projected points of the recommended camera placement with 1.5 px click noise: rmse_in 0.194 (cam0) and 0.185 (cam1), 0.02 to 0.03 s. Machine time for the whole calibration (2 x 20 s record + solves) is 43 s. The solved pose matched truth (tvec equal to 0.1 in at 1 px noise). Monte Carlo of the geometry (`dod6_d_montecarlo.txt`): triangulation error of independent points: opening center median 0.12 in, launch zone p95 1.15 in at 2 px click noise; at 3 px noise PnP RANSAC fails with the unhelpful message "PnP RANSAC failed: too few consistent points". The reported RMSE is small (0.05 to 0.22 in) so the "< 1 in" RMSE claim in the brief is trivially met; the independent-point error is the meaningful number.

Time judgement: machine time is negligible; the budget is human time: about 1.5 min per camera for intrinsics (waving the board 20 to 30 s) and 8 clicks per camera. Under 10 minutes is plausible once the UI list bug is fixed and the board is printed (the guide excludes printing from the budget, which is fair for a redo). With the bug it is not completable.

Webcam attempt (`dod6_a_webcam_intrinsics.txt`): Start/Stop intrinsics on the laptop webcam pointing at nothing returned 422 "Only 0 of 40 frames had a detectable 9x6 checkerboard for camera 'cam0'; need at least 8. Hold the board flat, fully visible, at varied angles and distances." Clear and actionable; stop call took 4.8 s on 40 frames at 640x480.

### DoD 6 weaknesses
- W7 (high, the refuting bug): UI point names hardcoded and out of sync with the backend (above). There is no test coupling `ui/app.js` names to `field_reference_points()` (not checked by me; a grep for it in tests was not done).
- W8 (medium): the "CELL opening center within 1 in of CAD" acceptance check has no UI; new guide section 5.4 says it is "run by the developer". The packaged app cannot do the check the guide's target line promises (the guide replaces it with a 3-ball replay check). So DoD 6 criterion "within 1 in" is not operator-verifiable.
- W9 (medium): the guide's acceptance (every point under 2 px, RMSE under 0.25 in) is tight versus realistic clicking. With 1.5 px click noise my run gave max per-point error 3.2 and 3.3 px (fails the "every point under 2 px" rule) although RMSE passed. In the UI the 1920 px image is displayed 640 px wide at a 1400 px viewport, so one screen pixel is 3 image pixels unless the operator zooms; expect redo loops that blow the 10 minute budget.
- W10 (medium): the guide's picture-position table (percent from left/top for each point) is hand-written from the simulation; it will be wrong for a real GoPro setup (placement is a draft) and was not verified against a real frame. Frame-top corner points 1 vs 5 are only about 40 px apart, easy to confuse.
- W11 (low): packaged zip `dist\HiveShotTracker_0.1.0_win64.zip` (15:30) predates the new endpoints and docs: no `/api/calib/checkerboard.pdf`, no `docs\` folder in `_internal`. Needs a rebuild before the guide is followable on the target PC. Also an RMSE of 3.97 in (cam0) from my first, unrealistic off-frame clicks was reported with HTTP 200 and saved: the API saves any solve, even a poor one, with no warning or threshold.
- W12 (low): `GET /api/calib/checkerboard.pdf` is cached in the data dir; if the board definition changes, a stale PDF is served.
- Docs `calibration.md` still says the red HIVE audience CELL must be "up" during calibration and assumes +Y audience; not checked against the real field (all numbers are VERIFY).

## Summary table

| Claim | Verdict | Blocking reason |
|---|---|---|
| DoD 1 | NOT REFUTED | none blocking; W1 (RTMP target must be a full URL, undocumented, URLs not shown in UI) should be fixed |
| DoD 6 | REFUTED | UI Calibration tab asks for 4 floor points that the backend rejects (422); fix `ui/app.js` to use `/api/calib/points`, then re-refute; also address W8 and W9 |

Cleanup statement: every process I started (run.ps1 app instances on 8770 and 8771, the packaged exe, mediamtx instances including one orphan, ffmpeg publishers) was stopped; ports 8770, 8771, 1935 are free. I made no changes to source files; I wrote only under `evidence/refute/` and the session scratchpad.

# HiveShotTracker HTTP/WebSocket API contract (v1)

Owned by the lead. Backend (hiveshot/app.py) and UI (ui/) both implement this exactly. Changes go through the lead.

Server: FastAPI on http://127.0.0.1:8765. Static UI served at `/` from `ui/`. All JSON. Units: inches, seconds, degrees, inches/second unless a key says otherwise (`*_mps` = m/s).

## Sessions
- `GET /api/sessions` → `[{session_id, name, started_at, ended_at|null, shots, made}]`
  - On server startup, sessions left open (`ended_at` null) by a previous run are ended (`ended_at` = now) before autostart creates a new one.
- `POST /api/sessions` body `{name}` → `{session_id}` (starts a new session and makes it current; ends any running one)
- `POST /api/sessions/{id}/end` → `{ok: true}`
- `GET /api/sessions/{id}/stats` → SessionStats as dict (see hiveshot/models.py SessionStats; `failure_order_hist` and `bounce_out_order_hist` keys are strings "1".."5")
- `GET /api/sessions/{id}/shots` → `[ShotSummary]` where ShotSummary = `{shot_id, t_launch, burst_id, burst_index, ball_type, result, exit_speed_ips, exit_speed_mps, launch_angle_deg, launch_azimuth_deg, apex_z_in, equation, clip_url|null}`
  - Classification: a track is `bounce_out` only when the ball leaves through the opening (an outward crossing of the opening plane inside the opening polygon); leaving the CELL box through any other face is `made` if it stayed inside for `settle_time_s`, else `unknown` with the note "track left the CELL through a wall (synthetic?)". A track that starts mid-flight is classified normally (its exit speed is measured from its first visible point).
- `GET /api/sessions/{id}/export.csv` → CSV download (stats.shots_to_csv)
  - CSV adds a `t_launch_wall` column (ISO 8601, blank when unknown); text cells starting with `=`, `+`, `-`, `@` are prefixed with a single quote to neutralize spreadsheet formulas.
- `GET /api/shots/{shot_id}` → full shot: ShotSummary plus `track: [{t,x,y,z}]`, `parabola: {a,b,c,rmse_in}`, `drag: {v0:[..], p0:[..], k_per_in, rmse_in}|null`, `launch_point:[x,y,z]|null`
- `GET /api/sessions/{id}/tips` → `[{t, alliance, new_up_cell, caused_by_shot_id}]`
  - ShotSummary additive fields: `dropped_during_flight` (int): frames the cameras dropped during the shot's flight (0 = none; also noted in the shot notes as "frames dropped during flight (N)"); `t_launch_wall` (string|null): ISO 8601 wall-clock launch time = session `started_at` + `t_launch`, null when the session start is unknown. A shot whose track ends mid-air or near the opening without evidence of a miss has `result: "unknown"` (notes: "track lost mid-air" / "track lost near the opening"), not `miss`.

## Cameras and pipeline
- `GET /api/config` → current config dict (sources, calibration file path, alliance, hive state, robot box dims, burst gap, thresholds)
- `PUT /api/config` body: partial config dict → full config after merge. Persisted to data/config.json. While the pipeline runs, a change to `sources` is rejected with 409; `burst_gap_s`, `settle_time_s`, `finalize_delay_s`, `stitch_gap_s`, `robot`, `preview_fps` and the HIVE state apply immediately, `detector` and `calibration_path` at the next start.
  - Validation (422, nothing applied or saved): every source `kind` must be `file|device|rtmp|url`, `cam_id`s must be non-empty and unique, `target` must be non-empty. For `kind: "rtmp"` a bare stream name such as `cam0` is accepted and resolved at start to `rtmp://127.0.0.1:1935/<name>`; a full URL is used as given.
  - `detector.motion_scale` (float in (0, 1], default 0.5): the motion (background-subtraction) model runs on the processed frame scaled by this factor, which halves the detector cost; 1.0 restores full-resolution motion. Applies at the next start.
- `GET /api/devices` → `[{index, width, height, fps}]` (ingest.list_devices)
- `POST /api/pipeline/start` → `{ok, running: true}`; `POST /api/pipeline/stop` → `{ok, running: false}`
- `GET /api/pipeline/status` → `{running, cameras: {cam_id: {fps, dropped, frames_read, is_alive, last_error, reconnects, props}}, detector_fps, last_shot_id, hive_state: {alliance, up_cell}, rtmp: {available, running, urls: {cam_id: url}}}`
  - `calibration_loaded` (bool, additive): true when intrinsics and extrinsics are loaded for both cameras. `warnings` (list of strings, additive): why the pipeline may produce no or poor shots, e.g. `no calibration loaded: 3D reconstruction disabled`, `camera cam1 resolution mismatch (1280x720 vs 1920x1080)`, `single-camera mode: ...`, stale extrinsics, per-camera errors, `camera cam0 dropped N frames (processing too slow)`.
  - `timing` (object, additive): moving averages of per-frame CPU stage times in ms, mean over cameras: `{detect_ms, track_ms, preview_ms, ring_ms, recon_ms}` (`recon_ms` is per reconstruction cycle); `timing_per_camera` has the same per-frame keys for each camera.
  - `timing` also carries `offset_s` (camera B -> camera A clock offset in use, null before the first estimate) and `offset_confidence` (0..1, the estimator's peak-versus-runner-up margin). The offset search is limited to +-0.1 s when both sources are devices on this PC, +-2 s for rtmp/url sources, +-0.5 s otherwise; an ambiguous estimate (confidence < 0.3) is revisited every 3 s instead of every 30 s.
  - `warnings` also reports ball tracks that found no partner in the other camera ("N ball track(s) could not be paired between the cameras and were dropped: shots may be missing").
  - `session_id` (string|null, additive): the session new shots are stored in; null after a session was ended (shots then go to the session `unassigned`). `calibration_mismatch` (object, additive): `{cam_id: "1920x1080 vs 1280x720"}` (calibration size vs delivered frame size), empty when consistent.
  - `cameras[cam_id].ended` (bool, additive): true when a file source reached end-of-file cleanly; such a camera reports `is_alive: false`.
- `GET /api/preview/{cam_id}.mjpg` → multipart/x-mixed-replace MJPEG stream of the latest frame with detections drawn (max 15 fps, 960 px wide); the JPEG is only encoded while at least one client is attached
- `GET /api/preview/{cam_id}.jpg` → single JPEG of the latest frame (for the calibration click UI)
- `POST /api/hive/state` body `{alliance, up_cell}` → sets the HIVE state manually (used until AprilTag detection is proven)

## Calibration
- `POST /api/calib/intrinsics/{cam_id}/start` and `/stop` → records frames for N seconds; `/stop` returns `{reprojection_rmse_px, frames_used}` and saves
- `POST /api/calib/extrinsics/{cam_id}` body `{points: [{u, v, name}]}` where name matches docs field point sheet → `{rmse_in, per_point: [{name, err_px}]}`
- `GET /api/calib` → current calibration JSON (calib.save_calibration format) Each extrinsics entry carries `stale` (bool, additive): true when new intrinsics were saved after the extrinsics were solved; re-solve them.
- `GET /api/calib/checkerboard.pdf` → the printable 10x7-square (9x6 inner corners), 1 in checkerboard as `application/pdf`, attachment filename `checkerboard_10x7_1in.pdf` (generated once into the data dir, then cached)
- `GET /api/calib/points` → `[{name, xyz: [x, y, z]}]` the ordered field reference points (click order, inches, field frame) accepted by `POST /api/calib/extrinsics/{cam_id}`
- `POST /api/calib/crosscheck` (body ignored) → `{points: [{name, xyz_measured: [x,y,z], xyz_expected: [x,y,z], error_in, residual_in}], max_error_in, within_1_in}`: triangulates every reference point clicked in both cameras in their last `POST /api/calib/extrinsics/{cam_id}` solves (the click sets are stored per camera in the calibration JSON under `clicks`, `{cam_id: [{name, u, v}]}`) and compares with the known field position. `within_1_in` is `max_error_in <= 1.0` (the operator's known-point check). 409 when either camera lacks calibration or stored clicks; 422 when no point was clicked in both cameras.
- `GET /api/field/geometry` → field.to_json() (HIVE wireframe, cell polygons for both states, field bounds) for the 3D viewer

## WebSocket
- `WS /ws` → server pushes JSON messages:
  - `{"type":"status", ...status dict as above}` every 1 s
  - `{"type":"shot", "shot": ShotSummary}` when a shot is finalized
  - `{"type":"tip", "tip": {...}}`
  - `{"type":"shot_updated", "shot": ShotSummary}` (additive) when a later shot changes an already-announced shot (burst re-assignment: `burst_id`, `burst_index`)
  - `{"type":"stats", "stats": SessionStats dict}` after each shot

## Static
- `/` → ui/index.html; `/vendor/*` → ui/vendor; `/clips/{file}` → data/clips

## Config dict shape
```json
{
  "sources": [{"cam_id":"cam0","kind":"file|device|rtmp|url","target":"...","width":1920,"height":1080,"fps_hint":60,"backend":"auto","loop":true,"realtime":true}],
  "calibration_path": "data/calibration.json",
  "alliance": "red",
  "hive_up_cell": "audience",
  "robot": {"length":18,"width":18,"height":18,"launch_exit_height":12},
  "burst_gap_s": 1.5,
  "settle_time_s": 0.75,
  "detector": {"min_radius_px":4,"max_radius_px":60,"pollen_hsv":[[..],[..]],"nectar_hsv":[[..],[..]],"motion_thresh":25},
  "preview_fps": 15,
  "stitch_gap_s": 2.0,
  "finalize_delay_s": 0.5
}
```

## Setup, auto-calibration and tuning (v1.1, 2026-10-10)

- `GET /api/setup/status` → `{cameras_detected: [{index,width,height,fps}], sources_configured: bool, calibration_loaded: bool, tags_seen: {cam_id: [tag_id,...]}, pipeline_running: bool, recommendations: [str]}` — the wizard polls this.
  - Implementation notes (additive): `tags_roll` `{cam_id: {cluster: {roll_deg, sign}}}` for the HIVE tag clusters in view (`sign` +1 = right side up = up CELL, -1 = flipped = down CELL; from the tag's field-frame up vector when the camera is calibrated, else from its in-image roll). `cameras_detected` is always filled: devices the running pipeline holds are reported from its own stream properties, every other index (0-5) is probed through `ingest.list_devices` (cached 30 s; indexes the pipeline has open are never probed), whatever the pipeline is doing. Recommendations are generated from the actual state (not in demo mode): no device detected ("plug in the cameras"), only video-file sources ("The sources are video files; use the Cameras step to pick real cameras."), a camera that dropped frames in the last minute ("camera X is dropping frames (N in the last minute): processing too slow; close other programs or lower the preview fps."), one source only, `camera X is at N fps; move it to its own USB port, not a shared hub.` (running device camera at >= 1080p below 59 fps), no calibration ("print the tag sheet ... Auto-calibrate"), tags seen per camera while uncalibrated.
- `GET /api/calib/tags.pdf` → printable letter-size kit, one page per AprilTag 36h11 tag (4 pages, ids 100–103, 6.0 in square, labeled with their frame corner: "frame top corner (-X,+Y)" etc.) plus a size check line; print at 100 % scale. Tag ids and sizes: `GET /api/calib/tags` → `[{id, size_in, name, xyz_center, corners_xyz}]`.
- `POST /api/calib/extrinsics/{cam_id}/auto` → detects the kit tags (and HIVE tags if `hive_tags: true` in the body and their layout is verified) in the latest frame, solves the pose, saves it, returns `{rmse_in, tags_used: [id], reprojection_px}`; 422 with a plain-language reason if fewer than 2 tags are visible.
  - Body `{source: "kit"|"hive"|"both"}` (default `both`; legacy `use_hive_tags: true` means `hive`): `kit` = the printed kit tags (ids 100-103), `hive` = the field's own HIVE tags at their computed (CAD) positions for the current HIVE state (learned tags only fill ids without a computed position), `both` = every detected tag with a known pose. Response `{rmse_in, tags_used, tags_missing, reprojection_px, max_corner_px, hive_tags_used, source, warnings}`; `warnings` holds "calibrated from HIVE tags only: expect 2-3x lower accuracy than the kit" when no kit tag was used. The kit corner pixels are stored as `clicks` ("tag 100 corner 0") so `POST /api/calib/crosscheck` works after auto-calibration.
- `POST /api/calib/auto_all` → runs auto extrinsics for every running camera, then crosscheck; returns per-camera results and `max_error_in`.
  - Response `{ok, results: {cam_id: {ok, ...auto response | status, error}}, crosscheck: {...}|null, max_error_in}`; 409 when the pipeline is not running.
- `POST /api/detector/sample` body `{cam_id, u, v, ball_type}` → samples a 9x9 HSV patch around the click on the latest full-res frame, widens the current range for that ball type to include it (with margins), persists it in config, returns the new range.
  - Response `{ball_type: "pollen"|"nectar", sampled_hsv: [h,s,v] (median of the 9x9 patch), range: [[lo],[hi]]}`. The range only ever widens: lo = min(old lo, sample - [8,40,40]), hi = max(old hi, sample + [8,40,40]), clamped to H 0-179, S/V 0-255. Persisted to `config.detector` and applied to the running detectors at once. 409 before frames exist, 422 for an unknown ball type or a click outside the frame.
- Config additions (defaults): `session_name_template: "Practice {date} {time}"`, `session_idle_end_min: 10`, `autosave_csv: true`, `profiles: {"arducam_1080p90": {...}}`, `default_intrinsics: {"arducam_2.3mp_110": {...}}` applied when a camera has no calibration (status.warnings says so).
  - Details: `profiles` values are config patches (`{"sources": [...]}`) to apply with `PUT /api/config`; `default_intrinsics` uses the first entry for any camera that has no intrinsics (`status.warnings`: "camera X uses default intrinsics (name); calibrate for accuracy"); `session_idle_end_min` 0 turns the idle end off; when a session ends idle the pipeline emits `{"type":"session_ended","session_id","reason":"idle","csv":path|null}`, writes `data/exports/<session name>_<session id>.csv` (if `autosave_csv` and the session has shots), and the next shot opens a new session named from `session_name_template` (a session ended by the user is NOT restarted: shots go to `unassigned`). `hive_tags_verified` (default false) enables inferring the up CELL from which CELL tag ids are visible while the cameras are not calibrated.
- Status additions: `hive_state_source: "manual"|"tags"`; when tags are visible on the up CELL the pipeline sets the HIVE state itself and logs tips.
  - `hive_state_source` is "tags" once the tags have decided (or both HIVE states were learned) and the user has not set the state manually since; `POST /api/hive/state` switches it back to "manual" until the next tag-confirmed state. The pipeline infers the state from the tags at ~2 Hz per camera (`tagkit.infer_hive_state`; computed up-CELL geometry as soon as the cameras are calibrated, learned tables once both states are learned) and commits a change after 3 agreeing samples spanning at least 250 ms, logging a tip.

## HIVE tag learning (v1.2, 2026-10-10)
- `POST /api/calib/hive_tags/learn` body `{state: {alliance, up_cell}}` → with both cameras calibrated, detects ids 30–45 in both latest frames, triangulates every tag corner seen in both, stores `hive_tags[state_key][id] = corners_xyz` in the calibration JSON; returns `{learned_ids, missing_ids, max_residual_in, visible_per_camera}`; 422 if fewer than 2 tags are seen in both cameras.
  - Response adds `up_cell_error_in` (additive): mean distance between the triangulated up-CELL tag corners of that state and the computed (CAD) ones, a sanity check of the whole calibration (null when the up CELL's tags were not seen by both cameras). `GET /api/calib/hive_tags` → `{alliance, states: {state_key: {tags: {id: {corners_xyz, center_xyz}}, row_height_in: {cluster: z}}}, ready, hive_state_source}`.
- `GET /api/calib/hive_tags` → the learned table per state plus `row_height_in` per cluster.
- Status: `hive_state_source` becomes "tags" automatically once both states are learned; `tags_seen` lists ids per camera. Tip events are then generated by the pipeline from state changes with 3-frame/250 ms hysteresis.
- HIVE-tag calibration and state inference work per camera: a camera that cannot read the HIVE tags is refused (`POST /api/calib/extrinsics/{cam_id}/auto` with `source: "hive"` → 422 "no HIVE tags visible to {cam}..."; `auto_all` reports it per camera with `ok: false`), and `hive_state_source` becomes "tags" as soon as at least one calibrated camera sees a cluster (right side up = up CELL) with the 3-sample/250 ms hysteresis. Only `hive_tags/learn` needs both cameras to see the tags.
- `POST /api/calib/extrinsics/{cam_id}/auto` body may include `{use_hive_tags: true}` to solve from learned HIVE tags for the current state (kit-free recalibration).

## Demo mode (v1.3, 2026-10-10, owner request)
- Runs with nothing external: two bundled synthetic videos (fixtures/synth_20 if present, else fixtures/synth_basic), realtime pacing, loop on, the calibration embedded in the fixture truth JSON, HIVE state manual (audience up), no RTMP server started, wizard suppressed.
- `python -m hiveshot.app --demo` (also the packaged exe `HiveShotTracker.exe --demo`): applies the demo config to a separate data dir `<data>/demo` (so real data is never touched), starts the pipeline, creates a session named "Demo {date} {time}", opens the browser.
- `POST /api/demo/start` → same from a running app: stops the pipeline, swaps to the demo config (in-memory, not persisted to config.json), starts, creates the demo session; returns `{ok, session_id}`. `POST /api/demo/stop` → stops the pipeline and restores the saved user config; returns `{ok}`.
- Status gains `demo: bool`. The UI shows a "DEMO" badge and a "Run demo" / "Exit demo" button in the top bar; while in demo the Setup wizard does not auto-open and the Settings tab shows a banner "demo config (not saved)".

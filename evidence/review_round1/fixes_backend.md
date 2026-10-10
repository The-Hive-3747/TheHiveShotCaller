# Backend fixes for review round 1

Owner: backend worker. Files: hiveshot/pipeline.py, app.py, store.py, shots.py (config.py, stats.py untouched), tests/test_pipeline.py, test_app.py, test_store.py, test_shots.py; docs/api.md (additive).

## Finding -> change -> test

| # | Change | Test |
|---|---|---|
| F1 | `set_hive_state(alliance, up_cell, t=None)` appends to a timestamped history `_hive_hist`; `_state_at(t)` looks it up. `_finalize` classifies (and extends into the opening, and stitch decisions) with the state at the shot's first 3D point time. Tips are created with `caused_by None` and kept in `_pending_tips`; after a MADE shot is stored `_link_tips` attributes a tip whose time lies in [t_launch, t_launch+3 s] and not earlier than entry-0.15 s, then `store.set_tip_cause`. `Store.add_tip` now returns the tip_id. | `test_made_shot_that_tips_hive_stays_made_and_links_tip` (synth_basic, flip injected 0.3 s after shot 1's last point via a `_finalize` hook; shot MADE, tip.caused_by == shot 1), `test_hive_state_history_lookup`, `test_link_tips_requires_window_and_entry`, `test_tip_ids_cause_update_and_ensure_session`. Mutation check: using the finalize-time state makes the F1 test fail (shot recorded as miss). |
| F2/F7 | `_life` RLock around `start`/`stop`; `start` returns `status()` and is a no-op when running (also on concurrent calls); start failure cleans up readers. `stop`: sets `_stopping`, joins all threads for up to 10 s (logs an error if exceeded), stops readers, then ONE final `_recon_cycle(final=True)` (includes chain flush) with no worker running, then clears state. `running` is false while stopping. `Store.close` idempotent; app lifespan closes the store in `finally` only after `stop` returned. | `test_concurrent_start_creates_one_set_of_threads` (4 threads via barrier: 2 `cam-`, 2 `lockstep-`, 1 `recon` thread; second stop is a no-op; no threads left) |
| F3 | Pipeline keeps `_desired` (latest) and `_rcfg` (snapshot taken at start; workers only use `_rcfg`). `apply_config(new)`: while running, a changed `sources` raises `ConfigConflict`; `burst_gap_s, settle_time_s, finalize_delay_s, stitch_gap_s, robot, preview_fps` and the HIVE state apply immediately; `detector`/`calibration_path` are reported as deferred to next start. `PUT /api/config` maps ConfigConflict to 409 (nothing saved or applied). `pipeline.cfg = x` is a setter routed through apply_config. | `test_apply_config_rejects_source_change_while_running`, `test_put_config_rejects_source_change_while_running` (409, config unchanged, burst/stitch applied, repeated start no-op) |
| F4 | `assign_bursts` strips its own `burst exceeds N balls (index M)` tag before re-adding. Pipeline compares the re-assigned bursts with the stored ones, persists only changed rows and emits `shot_updated` (ShotSummary) for changed shots other than the new one. docs/api.md WebSocket section documents `shot_updated`. | `test_assign_bursts_is_idempotent`, `test_assign_bursts_keeps_other_notes_and_drops_stale_tag`, `test_burst_changes_are_broadcast_consistently` (shot+shot_updated events end equal to the DB burst fields on synth_burst) |
| F6 | `_cam_loop` always calls `Tracker2D.finish()` on exit (stop or EOF) and queues those tracks; `stop` then runs the final recon cycle and flush. | `test_stop_mid_fixture_flushes_completed_shots` (stop once last_shot_id >= 2; every truth shot whose launch+duration_s <= the cameras' clock at stop minus 0.1 s must be stored; derived from shots.json). Mutation check: removing the final cycle makes it fail. |
| F8 | First delivered frame size per camera is recorded; intrinsics size is compared (warning once); `status()["calibration_mismatch"] = {cam: "1920x1080 vs 1280x720"}` (calibration vs frame). Calibration is read in pipeline with tolerance for a `stale` key on extrinsics. App: `intr_stop` saves with the camera's extrinsics flagged stale (`stale: true` written into the calibration JSON; `GET /api/calib` returns `stale` per extrinsics; solving extrinsics clears the flag). calib.py not edited: the flag is added to/stripped from the JSON by app/pipeline; note `calib.load_calibration` itself would reject an extrinsics dict containing `stale` (only pipeline loads the file). | `test_calibration_size_mismatch_reported`, `test_matching_calibration_reports_no_mismatch`, `test_intrinsics_save_marks_extrinsics_stale` |
| F10 | `_clock()` ignores cameras without a frame for > `STALL_AFTER_S` (2 s wall); all stalled -> latest source time. | `test_clock_ignores_stalled_camera` (unit), `test_stalled_camera_does_not_block_finalization` (cam1 reader hangs after 120 frames; shots that ended by 1.8 s finalize before the file ends), `test_unavailable_device_source_does_not_wedge_pipeline` (file + device 99; clock follows cam0, stop < 15 s) |
| F12 | `_finalize` no longer creates a session: with none active it stores to fixed session `unassigned` (`Store.ensure_session`, created already ended) and logs one warning ("no active session"); `status()["session_id"]` is current or null. Tips use the same fallback. | `test_shots_without_active_session_go_to_unassigned`, `test_session_end_is_visible_in_status_and_shots_go_unassigned`, `test_tip_ids_cause_update_and_ensure_session` |
| F13 | Ring length `max(3 s, stitch_gap_s + finalize_delay_s + 1 s)`; clip window for cam B shifted by the estimated offset (own clock); `VideoWriter` released in `finally`; frames whose size differs from the first are dropped with a logged warning; frame-size changes logged once per size. | No dedicated test (clip writing is off in tests via `save_clips=False`); covered by ruff/import only. |
| F14 | `test_pipeline_on_synth_fixture` now asserts exact shot count and exact made count; new websocket test; `test_geometry_devices_calib` monkeypatches `ingest.list_devices`. | `test_websocket_receives_shot_events` (ShotSummary key set equals docs/api.md), `test_geometry_devices_calib` |

Not changed (not in assignment): F5, F9, F11 (ingest/recon). `test_ingest` wall-clock flake note belongs to the ingest owner.

## Evidence

```
$ .venv\Scripts\python.exe -m pytest tests/test_pipeline.py tests/test_app.py tests/test_store.py tests/test_shots.py tests/test_stats.py -v
============================= 54 passed in 53.16s =============================

$ .venv\Scripts\python.exe -m pytest tests -q          (whole suite, other workers' files as they were at the time)
..........................................................ss............ [ 41%]
........................................................................ [ 82%]
..............................                                           [100%]      (2 skipped = live tests)

$ .venv\Scripts\python.exe -m ruff check hiveshot tests
All checks passed!
```

Mutation checks (temporary, reverted): classification with finalize-time state -> `test_made_shot_that_tips_hive_stays_made_and_links_tip` FAILED; removing the final recon cycle in `stop` -> `test_stop_mid_fixture_flushes_completed_shots` FAILED.

## Limits / caveats

- F10 integration with a never-opening device cannot produce 3D shots (only one working camera); the finalization assertion uses a camera whose reader hangs mid-file (patched `_LockstepReader.get`), plus a device-99 smoke test and a unit test of `_clock`.
- Tip attribution: the first finalized MADE shot satisfying the window/entry rule takes the tip; within a tight burst an earlier made shot can take a tip that a later one caused.
- The `intr_stop` stale marking is tested through `AppState.save_calib` with the same arguments `intr_stop` passes, not through a real chessboard recording.
- A shot launched before a HIVE flip but entering after it is classified against the pre-flip cell (as specified).

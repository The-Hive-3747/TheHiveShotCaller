# Independent review, round 1 (2026-10-10)

Reviewer: Opus-tier read-only worker. Gates run: pytest 131 passed, 2 skipped (live); ruff clean.
Files reviewed at pipeline.py md5 dd18847c (after the round-3 backend edits).

## Findings (ranked)
1. HIGH CONFIRMED. Made shot that tips the HIVE is recorded as MISS; tip loses caused_by_shot_id. _finalize reads HIVE state at finalize time (pipeline.py ~669-679), not shot time; set_hive_state (~254-258) looks for the causing shot before it is stored.
2. HIGH CONFIRMED. start()/stop() not serialized: _running checked at ~305, set at ~350 after readers open; double Start orphans capture threads; two recon threads mutate _chains without a lock.
3. HIGH/MED CONFIRMED. PUT /api/config while running swaps pipeline.cfg under live workers (app.py ~221-227); per-camera state built at start -> KeyError every cycle, silently no shots; reorder flips time-offset sign.
4. MED CONFIRMED. assign_bursts re-run appends duplicate "burst exceeds 4 balls" notes (shots.py ~117-121); changed earlier shots never re-broadcast; one commit per stored shot per new shot.
5. MED CONFIRMED. Realtime file that fails to open never sets finished (ingest.py ~221-222) -> _cam_loop spins forever.
6. MED CONFIRMED. Stop discards in-flight shots: no flush of open 2D tracks, no final recon cycle.
7. MED PLAUSIBLE. Shutdown race: stop() joins with 5 s timeout then flushes while recon may still finalize (double finalize); store.close() right after can hit ProgrammingError.
8. MED CONFIRMED. Calibration resolution never compared to delivered frame size; new intrinsics saved next to stale extrinsics without warning (app.py ~344-346).
9. MED CONFIRMED. One-to-one whole-track matching loses the second half of a flight that camera B splits (recon.py ~265-286; pipeline.py ~552-563).
10. MED/LOW CONFIRMED. _clock() = min over running cameras; one stalled camera freezes finalization (~465-482).
11. LOW/MED PLAUSIBLE. Live timestamps taken at read() return (ingest.py ~133) carry buffer jitter; _cam_fps trusts reported fps (RTMP/FLV may report 1000 -> tolerance 1.5 ms rejects all pairs).
12. LOW/MED CONFIRMED. After "end session", next shot silently auto-creates a session (app.py ~166-171, pipeline.py ~665-667).
13. LOW CONFIRMED. Clip ring buffer (3 s) shorter than max hold (~3.9 s); cam B clip window uses wrong clock; writer not released on write failure; size-changed frames dropped silently.
14. Tests: none of 1-9 covered; test_pipeline accepts ±1 made; wall-clock bounds in test_ingest may flake; test_geometry_devices_calib probes real hardware; no websocket shot-event test.

Checked OK: SQLite locking across threads, numpy JSON, unit conversions, parabola direction/angle, time-offset sign, track ending on the opening plane, detector on frame-size change.

## Top 3 fixes recommended
1. Timestamped HIVE-state history; classify at shot time; link tips after finalize.
2. Lifecycle lock, per-run config snapshot, reject source changes while running, final recon cycle and single flush after threads exit.
3. Idempotent burst assignment with re-broadcast; set finished on open failure; regression tests.

# Ingest fixes (round 1)

| Finding | Change (hiveshot/ingest.py) | Tests (tests/test_ingest.py) |
|---|---|---|
| F5 | CaptureThread sets finished=True (+last_error) when a FILE source fails to open; _run wrapped so any crash/exit of a FILE thread also sets finished. stats() gains "finished". | test_realtime_missing_file_sets_finished, test_file_eof_sets_finished |
| F11a | DEVICE frames: t_source = CAP_PROP_POS_MSEC/1000 if non-zero and increasing, else None; t_capture unchanged. stats() gains latency_estimate_s (median of last 60 intervals of dt-1/fps, >=0; diagnostic only). | test_device_t_source_from_pos_msec, test_device_t_source_none_when_zero, test_latency_estimate_stats |
| F11b | props(): fps <=0, >240, NaN replaced by measured fps (after _FPS_MEASURE_AFTER_S=2 s) else fps_hint or 30; raw in fps_reported. Capture thread refreshes props every 30 frames. | test_props_fps_sanity_fallback (1000/0/-5/NaN), test_sane_fps_passthrough |
| F14 | Tests only: stop bounds <5 s; pacing = lower bound 0.8 s + 10 s hang guard, fps band 15..45; commented. | test_slow_consumer_drops_oldest, test_multicapture, test_realtime_pacing |

All changes additive; public signatures unchanged. rtmp_server.py untouched.

## pytest
```
...........ss...........                                                 [100%]
```
## ruff
```
All checks passed!
```

## Addendum: dod1_dod6_1 items
- list_devices: index 0 probed with new `first_index_timeout=2.5` (others `per_index_timeout`, default 1.0); last non-empty result cached 30 s (`use_cache=False` bypasses; empty results never cached). Tests: test_list_devices_cold_first_index_and_cache, test_list_devices_empty_not_cached.
- RtmpServer.start(): port already listening -> if `tasklist /FI "IMAGENAME eq mediamtx.exe"` shows PIDs, adopt (warning logged, `adopted=True`, is_running() true while port listens); else RtmpServerError "RTMP port N busy by another process". stop() never kills adopted processes unless `kill_adopted=True` (new ctor kwarg, default False), then `taskkill /PID`. Tests: test_rtmp_port_busy_other_process (dummy socket on ephemeral port), test_rtmp_adopts_orphan_and_stop_does_not_kill, test_rtmp_adopted_killed_only_with_kill_adopted, test_rtmp_mediamtx_pids_parses_tasklist.
- Final run: pytest `...........ss.................` (2 live skips), ruff `All checks passed!`

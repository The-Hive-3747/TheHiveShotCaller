# Current handoff (lead)

Updated: 2026-10-10 ~17:10 (session 1, paused by owner for an offline period)

## Where things stand
- Repo: https://github.com/The-Hive-3747/TheHiveShotCaller.git, branch main. Last pushed commits: phase 1 import, WIP CAD geometry, README. This checkpoint commit adds everything below.
- Field geometry is CAD-grounded (hiveshot/field.py reads field_constants; red HIVE at +X; opening y=15.77; tag poses computed for both CELLs). All four fixtures regenerated (synth_basic, synth_burst, synth_20, synth_240), evidence/m1_field/synth_cli.txt has the commands.
- Detection/tracking updated for the new fixtures: 25 tests pass, recall >= 0.95 on all four (evidence/m2_detect/).
- Recon: alias-robust time offset (choose_offset_by_epipolar) done, 18 tests pass.
- Tag kit, HIVE-tag defs, learn/verify, infer_hive_state: done (tests pass).
- UI: wizard (Cameras, Tags with kit/no-printer choice, Verify HIVE tags, Colors, Done), demo button/badge, session picker, warnings banner, cross-check, ENDED/dropped indicators: static tests + Node syntax gate pass (29 tests).
- Packaging: spec bundles VC++ DLLs, docs, both fixtures; demo smoke test ready; needs a rebuild.
- Two workers were STOPPED mid-task at the owner's request (their partial edits are in the tree, uncommitted until this checkpoint):
  1. Placement re-run (hiveshot/placement.py, docs/camera_placement.*, tests/test_placement.py): asked to re-optimize with (a) HIVE tags readable by >= 1 camera, (b) triangulation >= 75°, (c) min lens height 20 in, (d) robot-box occlusion, (e) prefer wall corners. The last complete result (both cameras on the audience wall, 62°, 12 in height) is NOT accepted. State of files unknown: re-run `pytest tests/test_placement.py` first.
  2. Backend worker (pipeline.py, app.py, config.py, shots.py, stats.py, store.py and tests): long queue partly done. Done per its last reports: perf stage timers, mid-air-lost -> UNKNOWN, dropped_during_flight, checkerboard/points routes, stale-session close, CSV hardening. Possibly partial: setup/status, auto-calibration routes, detector/sample, smart defaults, HIVE-tag state, demo mode, DoD2 fixes (offset window, end-of-stream flush, bounce-out rule, synth_20/synth_240 pipeline tests). Check `git diff HEAD~1 -- hiveshot/app.py hiveshot/pipeline.py` and run `pytest tests/test_app.py tests/test_pipeline.py tests/test_setup.py tests/test_demo.py -q` to see what exists.

## Resume plan (in order)
1. `.\test.ps1` to get the real failure list (expect some from the stopped workers).
2. Relaunch a backend worker with the remaining items from docs/api.md v1.1-v1.3 (setup, auto-calib routes incl. source kit|hive|both, detector/sample, defaults, HIVE-tag state, demo mode) and the DoD2 fixes (evidence/refute/dod2_3_7_1.md), telling it what already exists.
3. Relaunch the placement re-run with the five constraints above.
4. Full suite green -> `powershell -ExecutionPolicy Bypass -File build.ps1` -> browser pass 3 (wizard, demo) -> refuters for DoD 2, 3, 6, 9, 10 -> phase commit + push.

## Owner actions pending
- QUESTIONS.md #5 clean-machine test (after a green build); #4 robot dimensions; hardware arriving Oct 11-20.
- holtb invited as collaborator (write), pending acceptance.

## Rules learned
- Never git stash/checkout while workers run (reverted edits once). Commit the tree as-is first.

## Round 7 (resumed after owner offline period)
- Fixtures regenerated consistently (consistency test added); detection/tracking green on all four; recon plane-fallback tests fixed; detector learningRate robustness added.
- Placement FINAL: cam0 (-78,+65) lens 30 in; cam1 (+65,+78) lens 20 in; 105° triangulation; cam1 is the HIVE-tag reader; robot occlusion modeled; kit tags now 6 in (3 readable per camera, pose 0.21 in / 0.13°). docs/camera_placement.* and docs/calibration.md regenerated.
- Waiting on: backend worker (restore green pipeline on new fixtures, DoD2 fixes, setup/auto-calib/sample/defaults, HIVE-tag state, demo mode). Then full suite -> build.ps1 -> browser pass 3 -> refuters 2,3,6,9,10 -> phase commit.
- 18:40 Browser pass 3 done (evidence/m4_e2e/browser_pass_3.md). build.ps1 failed only on its own stale-dist smoke gate (packaging worker reordering). CRITICAL finding: realtime headroom insufficient (PLAN.md section 12); performance task queued to the backend worker. Refuters and the phase commit wait for a green build and the perf fix.

- 20:00 Perf fix landed and verified (zero drops, stats exact). Gated build.ps1 running; physics/detect owners reviewing the backend's cross-file perf edits. Next: phase commit + push, refuters 2,3,6,9,10, then DoD status update.
- 20:50 Phase 2 committed/pushed (6e2fe2a). Refuter round 2: DoD 9 REFUTED (modeled frame corners do not exist); real A-frame now in field.py from the STEP (crossbar 24 in at z 41.45; base corners ±24.73/±19.47); kit/click points/placement being redone on real features (tagkit worker); crosscheck now out-of-sample; field_size_in setting added (UI input in progress); docs refreshed. Refuters for DoD 2/3 and 6/10 running. Next: full suite -> rebuild -> re-refute 9 -> phase 3 commit.

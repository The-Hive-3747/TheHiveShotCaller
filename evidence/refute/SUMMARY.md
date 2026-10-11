# Refuter pass 1 summary (2026-10-10)

| DoD | Verdict | Report | Follow-up |
|---|---|---|---|
| 1 one command, USB + RTMP | NOT REFUTED | dod1_dod6_1.md | weaknesses assigned: RTMP stream-name targets, config validation, warnings in status, orphaned MediaMTX adoption, device probe timing |
| 2 20-shot session stats | REFUTED | dod2_3_7_1.md | time-offset aliasing on periodic bursts (recon), lost shots at end of last burst (pipeline), bounce-out rule, 20-shot regression fixture |
| 3 accuracy on labeled footage | REFUTED | dod2_3_7_1.md | detection holds (0.97-1.00); make/miss and speed fail when the offset is wrong (same root cause); all footage synthetic: needs real recordings after hardware arrives |
| 4 every shot replays in 3D | NOT REFUTED | dod4_5_1.md | cosmetic items fixed (unknown filter, no-track message) |
| 5 persistence and CSV | NOT REFUTED | dod4_5_1.md | stale sessions closed at startup, CSV formula neutralization, wall-clock column (in progress) |
| 6 calibration under 10 min | REFUTED | dod1_dod6_1.md | stale point list in the UI (fixed: UI now fetches /api/calib/points); tag-kit auto-calibration added to make it one button |
| 7 tests + live E2E evidence | REFUTED | dod2_3_7_1.md | unit/integration coverage holds; no live-camera run exists and cannot until hardware arrives (expected 2026-10-11 to 10-20) |
| 8 clean-machine smoke | REFUTED | dod8_9_1.md | owner action (QUESTIONS.md #5); VC++ DLLs and docs now bundled |
| 9 placement yields calibration | REFUTED | dod8_9_1.md | geometry conflict fixed (single source of truth), 8 visible reference points, docs rewritten; re-refute pending |

Re-refute after the fixes land: 2, 3 (synthetic part), 6, 9, and the new 10 (wizard).

# Refuter pass 2 (2026-10-10 evening, on commit "Phase 2")

| DoD | Verdict | Report | Follow-up |
|---|---|---|---|
| 9 placement yields calibration | REFUTED again | dod9_2.md | Modeled frame "top corners" (z=63.95) do not exist: the official frame is an A-frame with apex ~44 in + crossbar. Kit anchors, click points, roll check and occlusion wireframe all move to real CAD features (field worker -> tagkit/placement worker). Also: wall inside face CAD ±70.7 vs manual ±72 (field_size setting + measure), crosscheck must be out-of-sample, tripod feet placement, stale numbers in PURCHASE_LIST/operator guide. Map/doc/recommend consistency and CELL/tag geometry (0.02 in) held. |
| 2, 3 | running | dod2_3_2.md | |
| 6, 10 | running | dod6_10_2.md | |

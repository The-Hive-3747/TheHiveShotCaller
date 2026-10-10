# Current handoff (lead)

Updated: 2026-10-10 15:50 (session 1)

## State
- M0–M4 implemented and verified on synthetic fixtures. Full suite: 126 passed, 2 live skipped, ruff clean (evidence/run_20261010_145024 and later runs).
- Browser pass done by lead against the real backend (evidence/m4_e2e/browser_pass_1.txt): dashboard, shots table, CSV export, 3D replay, restart persistence all OK. Measured speeds/apex/made-miss match fixture truth exactly.
- Round 3 workers running (disjoint ownership):
  - pipeline/app/store: synth_burst pipeline test, finalize delay, restart E2E, `ended` status key
  - ui/: responsive replay layout, session picker, ENDED state, shot filter, follow-ball
  - independent reviewer (read-only) -> evidence/review_round1/report.md
  - packaging (PyInstaller), hiveshot/resources.py, docs/operator_guide.md, docs/troubleshooting.md -> evidence/m5_build/

## Decisions
- See PLAN.md section 8 and QUESTIONS.md. Field frame: origin field center on tiles, Z up, X toward audience, Y along beam, audience CELL at +Y.
- Pipeline heuristics (fragment stitching, extrapolation into the opening) are tuned on synthetic data only.

## Next
- Integrate review findings; route resources.py call sites; re-run test.ps1; rebuild; final E2E in browser; update PLAN.md status and QUESTIONS.md.

## Unresolved
- Official CAD numbers (VERIFY in field_constants.py); AprilTag corner geometry placeholder; real-ball HSV ranges unverified; no real camera footage yet.

## Round 4 (in progress)
- Review round 1 report: evidence/review_round1/report.md (13 findings). Fix workers running: backend (F1,2,3,4,6,7,8,10,12,13,14), ingest (F5,11,14), recon (F9), UI (shot_updated, ordering, mismatch chip, tips list).
- After round 4: full test.ps1, rebuild via build.ps1, browser pass 2, then refuter pass per DoD item (PLAN.md section 11).

## Round 6 (2026-10-10 16:20)
- Official field geometry read from the manual figures and assembly guide (docs/research_apriltags.md, docs/official/). Up-CELL HIVE tags computable; down-CELL learned; placement to be re-optimized for tag visibility (lower cameras).
- Refuter pass 1 summary: evidence/refute/SUMMARY.md. Root cause of DoD 2/3 failures: time-offset aliasing on periodic bursts (recon fix dispatched) + end-of-stream chain loss (pipeline fix queued).
- In flight: field worker (hive_tag_corners, down-cell reconciliation, STEP extraction), tagkit/placement worker (computed tags, tag-visibility placement), backend worker (long queue: perf, calib routes, setup, hive tags, DoD2 fixes), recon worker (offset aliasing, synth_20 fixture), UI worker (wizard tweaks).
- Next: full suite, build.ps1, browser pass 3 (wizard), re-refute 2,3,6,9,10.

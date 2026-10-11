# HiveShotTracker — Plan, Milestones, Definition of Done

Status: DRAFT v0.1 (2026-10-10). Items marked **[Q]** depend on owner answers and will be revised.

## 1. Goal

A local desktop application that ingests two GoPro video feeds (wired capture card or wireless RTMP) aimed at the BIOBUZZ HIVE, detects each ball launched by the robot, decides whether it scored in the up-facing CELL, and produces:

- Shot count, make count, make rate (overall, by ball type, by session).
- Failure-order frequency: of shots that missed, how often the miss was ball 1, 2, 3 or 4 in its burst.
- Per-shot exit speed, launch angle, and fitted trajectory (parabolic equation plus a drag-corrected fit).
- A 3D replay viewer showing the field, HIVE, robot, and the reconstructed ball path for any recorded shot.

## 2. Ground truth about the field (verify against official CAD before M2)

| Item | Value | Source |
|---|---|---|
| Field | 144 x 144 in, 36 tiles of 24 in | Competition Manual 9.2 |
| HIVE structure | Centered on field; frame approx 49.46 x 38.95 in; pivot 43.95 in high | Manual 9.6, fan transcriptions |
| CELL opening | approx 20 x 14 in, tilted 30 deg; up-CELL opening center approx 59.5 in high | Manual Fig 9-11, fan transcriptions |
| HIVE behavior | Bi-stable; tips when enough mass lands in up CELL, contents spill, other CELL becomes target | Manual 10.5.1 |
| POLLEN | approx 2.8 in dia, approx 25 g, polyethylene, 40 on field | Manual 9.8, AndyMark am-5851 |
| NECTAR | approx 3.6 in dia, approx 41 g, polyethylene, 16 on field | Manual 9.8, AndyMark am-5852 |
| AprilTags | 36h11, 3.25 in, four per CELL bottom | Manual 9.9, Fig 9-17 |
| Robot limit | Max four scoring elements held at once | Manual G-rules |

## 3. Architecture (proposed)

```
 GoPro A ──┐  (HDMI->capture card, or RTMP->local server)
 GoPro B ──┤
 [Cam C]  ─┘  optional third camera (see 6)
     │
     ▼
 Ingest layer ─────────► frame queue (timestamped, per camera)
     │
     ▼
 Detector (color + motion + size) ─► 2D ball tracks per camera
     │
     ▼
 Sync + Triangulate (calibrated stereo) ─► 3D ball track in field coords
     │
     ▼
 Shot segmenter ─► launch point, exit velocity, arc fit, make/miss, burst index
     │
     ▼
 Store (SQLite + clip files) ◄──► Web UI (stats, live view, 3D replay)
```

**Stack [Q]:** Python 3.11+, OpenCV, NumPy, FastAPI; UI in browser with Three.js for the 3D viewer. RTMP ingest via a bundled MediaMTX binary that GoPro streams into and OpenCV reads from. SQLite for shots. No cloud, no accounts.

Alternative if Python is unwanted: Node + a native capture binding. Python is recommended because OpenCV tooling is far more mature there.

## 4. Milestones

Each milestone ends with a demo you can run and a short evidence file under `evidence/<milestone>/`.

### M0 — Environment and skeleton (small)
- Install runtime, create project layout, dependency lockfile, one-command run script.
- Ingest one video source (file first, then capture card or RTMP) and display it with timestamps.
- Populate the Project-specific configuration section of CLAUDE.md.
- **Exit:** `run` opens a window or page showing both camera feeds, or a recorded file, with per-frame timestamps and dropped-frame counter.

### M1 — Calibration and field model (medium)
- Intrinsic calibration per camera from a checkerboard video.
- Extrinsic calibration by clicking known HIVE frame points or by detecting the HIVE AprilTags.
- Field coordinate system fixed: origin at field center on the tile surface, X toward audience side, Z up (to be confirmed against official CAD convention).
- 3D field model: tiles, HIVE frame, both CELLS in both tip states, generic robot box.
- **Exit:** reprojection error under 2 px per camera; a known point (e.g. CELL lip corner) triangulates within 1 in of its CAD value.

### M2 — Ball detection and 2D tracking (medium)
- Detect POLLEN and NECTAR by color, size and motion; classify type.
- Track across frames with a Kalman filter; handle occlusion by HIVE frame and robot.
- Works on recorded test footage at 30, 60 and 240 fps.
- **Exit:** on a labeled test clip of at least 40 shots, at least 95 percent of balls detected in each view with no more than 1 false track per minute.

### M3 — Stereo reconstruction, shot segmentation, physics (medium to large)
- Time-align the two feeds (visual sync event; no trust in stream clocks).
- Triangulate 3D ball positions; fit a parabola and a drag-corrected arc per shot.
- Report exit speed, launch angle, apex, and the equation y = a x^2 + b x + c in the shot plane.
- Decide make/miss [Q: entry vs settled], detect bounce-out, and assign burst index 1 to 4.
- Detect HIVE tip events.
- **Exit:** on a test clip with a tape-measured target, exit speed agrees with a hand-timed high-speed reference within 10 percent at 60 fps and within 5 percent at 240 fps; make/miss matches human labels at least 95 percent.

### M4 — Statistics and UI (medium)
- Live dashboard: shot count, makes, make rate, by ball type, by session.
- Failure-order histogram (ball 1 to 4) for missed shots.
- Shot table with per-shot speed, angle, result, clip link.
- 3D replay: field, HIVE in correct tip state, robot, animated ball along reconstructed path; scrub, slow motion, camera orbit.
- Session management: start, stop, name, export CSV.
- **Exit:** full end-to-end run on live cameras produces correct stats for a 20-shot practice session and the replay opens for each shot.


### M4.5 — Guided setup and smart defaults (owner request 2026-10-10)
- Printed AprilTag calibration kit (four 36h11 tags at the HIVE frame top corners) and one-button auto-calibration per camera; cross-check shown in the UI.
- First-run setup wizard: detect cameras, assign cam0/cam1 by clicking previews, apply the Arducam 1080p90 profile, auto-calibrate, click-to-sample ball colors, start the first session.
- Smart defaults: session name template, idle auto-end with CSV autosave, shipped default intrinsics for the Arducam lens (warning until calibrated), plain-language recommendations in status.
- HIVE tag learning: after kit calibration, triangulate the field's own CELL tags in both settled states (owner flips the HIVE once); then HIVE state and tips come from the tags automatically and cameras can be recalibrated from the HIVE tags alone (docs/research_apriltags.md).
- **Exit:** a new user with the hardware list and the printed sheets reaches a running, calibrated session from a fresh install in under 15 minutes following only the wizard; refuter confirms.

### M5 — Hardening and release (small to medium)
- Dropped-stream recovery, RTMP reconnect, capture-card hot plug.
- Performance: sustained real-time at the chosen frame rate on the target PC.
- Packaged artifact (installer or zip) and smoke test on a clean machine.
- Operator guide: calibration and troubleshooting.
- Camera placement map and placement instructions: a top-down field diagram with tripod positions, heights, aim points and lens settings for all three cameras, plus a step-by-step placement checklist (owner-requested deliverable, 2026-10-10). Draft produced in M1 so test footage is shot from the final positions; finalized in M5.
- **Exit:** Definition of Done fully met.

## 5. Definition of Done

The project is done when all of the following are true and documented in `evidence/`:

1. The application starts with one command on the target Windows PC and runs with two GoPros over both a capture card and RTMP, switchable in settings.
2. A 20-shot live practice session produces: total shots, makes, make rate, per-ball-type breakdown, failure-order histogram, and per-shot exit speed, launch angle, and fitted equation.
3. Measured accuracy on labeled test footage: ball detection at least 95 percent per view; make/miss agreement at least 95 percent; exit speed within 10 percent at 60 fps and 5 percent at 240 fps against a reference.
4. Every recorded shot can be opened in the 3D viewer and replayed with field, HIVE, robot and ball path.
5. Data persists across an application restart. Sessions export to CSV.
6. Calibration can be redone by the operator in under 10 minutes following the guide.
9. A camera placement map and placement instructions exist in the project folder, and a fresh setup following them yields calibration within the M1 accuracy target.
10. A fresh install can be brought to a running, calibrated session through the setup wizard alone, using the printed tag kit, in under 15 minutes (M4.5 exit).
7. Unit tests cover the physics fit, shot segmentation, burst indexing and stats; integration tests run the pipeline on recorded fixtures; one end-to-end run on live cameras is recorded as evidence.
8. The packaged build has been smoke-tested on a clean machine.

## 6. Proposed additions (owner to accept or reject)

- Third camera above or behind the robot to resolve CELL entry vs lip bounce and to measure exit speed at higher frame rate (cheap USB global-shutter camera at 120 fps or more).
- Post-match high-speed mode: analyze 240 fps files recorded on the GoPro SD card for precise speed, in addition to live mode.
- AprilTag-based HIVE localization and tip-state detection.
- Ball-type classification (POLLEN vs NECTAR) and separate stats.
- Per-shot clip saving for replay.

## 7. Known risks

- GoPro live outputs are 30 to 60 fps; exit-speed accuracy from live feeds is limited.
- Wireless RTMP adds seconds of latency and no cross-camera sync; handled by visual sync.
- Spin and drag make real arcs non-parabolic; the parabola is reported as requested but the drag fit is more accurate.
- Occlusion by the HIVE frame near the CELL opening; mitigated by camera placement and the third camera.
- Python is not currently installed on this PC.

## 8. Owner decisions (2026-10-10)

- Cameras not yet purchased; owner asked for model recommendations (see 9).
- Target PC: this PC (owner's Windows 11 machine).
- Python stack approved; installing Python on this PC is authorized.
- Third camera approved if needed; owner asked for a recommendation.
- Camera mounting: tripods preferred, open to better options.
- Practice field only. No event-day constraints.
- MVP: robot stationary when shooting. Shoot-while-driving is a stretch goal (M6).
- Robot in viewer: box with owner-supplied dimensions. CAD import is a later nice-to-have.
- Make/miss: a shot counts as made only if the ball stays in the CELL. Bounce-outs are tracked as their own outcome and reported in stats.

Confirmed by owner (2026-10-10, second round):
- Exit speed is measured at the first frame the ball is clearly visible after leaving the robot. A colored marker on the launcher exit is optional and will refine the launch point.
- Failure-order index resets after each shooting burst (gap of more than 1.5 s starts a new burst; threshold adjustable in settings).
- HIVE tip events are logged as their own event with a timestamp and the shot that caused them.
- Git: not now. The folder stays a plain directory until the owner asks for a repository. Versioned evidence directories substitute for commits in the meantime.
- Budget: no fixed cap. Prefer speed; use parallel workers where the work is independent; avoid waste.
- CLAUDE.md project-specific configuration: populate during M0 once the stack is installed and commands exist.

- Calibration state (lead decision 2026-10-10 after refuter dod9_4): calibration is done with BOTH audience CELLs tipped up (field.CALIBRATION_STATE) so no CELL body hides the kit tags; ball tracking and tag reading assume the match-start state. Click points 5-8 are the blue audience up-CELL corners.

## 9. Hardware recommendation

**Primary cameras (two):** GoPro HERO13 Black, each with the GoPro Media Mod (for micro-HDMI out) and an Elgato Cam Link 4K capture card. Live HDMI output is 1080p60 when not recording, 1080p30 while recording. Turn HyperSmooth off for low latency. Wireless RTMP goes through the GoPro Quik app at 1080p30 and is supported as the fallback mode. Record 1080p240 to the SD card in parallel for the post-match high-speed analysis mode.

**Third camera (exit-speed and CELL-entry camera):** Arducam 2.3 MP global-shutter color USB camera, 1080p at 90 fps (Amazon B0FLX2DSSS). Global shutter avoids the skew that rolling-shutter cameras put on fast balls. Mount it on a tripod behind and above the robot, looking along the shot line toward the HIVE, on a 16 ft active USB extension. Full list with links: SHOPPING_LIST.md.

**Mounting:** Tripods outside the field wall, cameras at about 50 to 60 in height so the up-CELL opening is seen edge-on from one camera and face-on from the other. Mark tripod foot positions on the floor with tape so recalibration is rarely needed.

## 10. Stretch milestone

### M6 — Shoot while driving
- Track robot pose per frame using a colored marker set or an AprilTag on the robot.
- Report shot statistics against robot speed and heading.
- Not part of the Definition of Done.

## 11. Refuter pass (owner instruction, 2026-10-10)

After each Definition of Done item is claimed complete, the lead launches an independent refuter agent. The refuter receives only the DoD item text, the evidence path and the repo; it must try to refute the claim by running the application and tests itself, constructing adversarial inputs, and checking the evidence against the code. It reports REFUTED (with reproduction) or NOT REFUTED (with what it tried). A REFUTED item returns to implementation and is re-refuted after the fix. Reports live in evidence/refute/<dod_item>_<n>.md. An item counts as done only after a NOT REFUTED report on the current code.

## 12. Risk register update (2026-10-10 evening)
- REAL-TIME HEADROOM: RESOLVED 2026-10-10 20:00 (evidence/m5_perf/round2.md, idle_realtime_headroom_after.txt). Root causes were GIL-holding bursts at shot finalization (drag fit 150-280 ms, clip copy under the capture lock), the 15.6 ms Windows timer tick batching frames, and per-frame color work. After the fix: zero dropped frames at 1080p60, 720p60 and 720p240 on a cool start with all shots correct; detect 1.6-4 ms/frame; recon cycles 35-200 ms. Remaining caveat: back-to-back 240 fps runs on this laptop drop 17-20 percent from thermal/power limits (not a pipeline wait). Verified independently by the lead.

## 13. Definition of Done status (updated 2026-10-11 01:30, synthetic data only; real cameras arrive Oct 11-20)

| DoD | Status | Latest refuter report | Open |
|---|---|---|---|
| 1 one command, USB + RTMP | NOT REFUTED (round 1) | evidence/refute/dod1_dod6_1.md | real cameras |
| 2 20-shot session stats | NOT REFUTED (round 2) | dod2_3_2.md | fast low-arc shots > 490 in/s (hardening in progress) |
| 3 accuracy targets | NOT REFUTED on synthetic (round 2) | dod2_3_2.md | real labeled footage |
| 4 3D replay | NOT REFUTED | dod4_5_1.md | - |
| 5 persistence, CSV | NOT REFUTED | dod4_5_1.md | - |
| 6 recalibration < 10 min | REFUTED narrow (round 3) | dod6_10_3.md | pair-gate lock-out, poor-lens acceptance, in-sample finish (fixes in progress) |
| 7 tests + live E2E evidence | REFUTED | dod2_3_7_1.md | live-camera run (hardware) |
| 8 clean-machine smoke | REFUTED | dod8_9_1.md | owner runs docs/clean_machine_test.md |
| 9 placement -> calibration target | NOT REFUTED (round 5, 2026-10-11) | dod9_5.md | real-field verification when hardware arrives |
| 10 wizard-only setup < 15 min | REFUTED on time (round 3) | dod6_10_3.md | 18-26 min with Lens step; QUESTIONS.md #9 |

# Realtime headroom, round 2 (2026-10-10)

Machine: Intel Core Ultra 9 285H laptop (6 P + 8 E + 2 LP-E cores, no hyper-threading), Windows 11,
"Balanced" power plan, Python 3.12.10, OpenCV (bundled FFmpeg). All numbers: `Pipeline` with
`realtime=True` file sources (the real capture threads, detectors, trackers, reconstruction, shot
fitting, clip writing; no UI client unless stated). Harness: `evidence/m5_perf/rt_run.py`
(cool-start protocol: `cool_runs.py`, 40 s idle before every run).

## Result (cool start, 3 runs per fixture; raw: `round2_cool_runs.txt`, `round2_final_cool.txt`)

| fixture | frames dropped BEFORE (per camera) | frames dropped AFTER | shots AFTER |
|---|---|---|---|
| synth_basic 1080p60 (164 frames) | 25-27 (15-16 %) | 0 / 0 / 0 | 6/6 stored, 4 made = truth in 3/3 runs (BEFORE: 3 made in 1 of 3 runs) |
| synth_20 720p60 (1005 frames) | 118-141 (12-14 %) | 0 / 0 / 0 | 20/20, 14 made = truth in 3/3 (BEFORE: 13 made in 2 of 3) |
| synth_240 720p240 (782 frames) | 177-234 (23-30 %) | 0 / 0 / 0 | 8/8, 6 made = truth in 3/3 (BEFORE: 5 made, or 7 of 8 stored, in 3/3) |
| synth_240 with MJPEG preview clients on both cameras | - | 0 | 8/8 correct |
| synth_20 with preview clients | - | 0 | 20/20 correct |

BEFORE = the checkpoint commit 449f900 plus the one-line `_LowResMotion.apply(learningRate=)` crash fix
(without it the pipeline read no frames at all).

`status.timing` (mean ms per frame per camera, final sample):

| fixture | detect_ms before -> after | track_ms | ring_ms | recon_ms per cycle |
|---|---|---|---|---|
| synth_basic | 13.2-14.2 -> 3.2-3.8 | 0.3-1.2 -> 0.2 | 0.5-0.9 -> 0.2 | 270-285 -> 35-41 |
| synth_20 | 7.3-7.7 -> 1.3-1.5 | 0.2-0.6 -> 0.1 | 1.1-1.8 -> 0.2 | 273-297 -> 34-36 |
| synth_240 | 4.4-6.0 -> 1.3-1.4 | 0.2-0.4 -> 0.1 | 0.9-1.5 -> 0.2 | 500-510 -> 167-175 |

Isolated detector benchmark (shrink + detect, single thread, 3902 frames from three fixtures):
1.60 ms -> 1.08-1.2 ms per frame; detections identical frame by frame (`detect_equiv.py`).
The idle-machine figure of ~32 ms `detect_ms` in `idle_realtime_headroom.txt` is the same effect
as BEFORE here: the isolated cost is 1-2 ms, the rest was waiting for other threads.

## What was wrong (measured, not assumed)

Sampling profiler (`rt_sample.py`, `sys._current_frames` every 4 ms) and per-frame instrumentation
(`rt_exp2.py`, `rt_exp4.py`) showed: the camera threads were idle 59 % of the time, yet frames were
dropped in bursts of ~100-130 ms that coincided with a shot being finalized. Causes, in order of impact:

1. **Drag fit held the GIL** (`physics.fit_drag`): pure-Python RK4 on tiny numpy arrays, 100+
   integrations per fit, 150-280 ms per shot (3 ms per integration). Every cv2 call of a camera
   thread then waits for the GIL again (convoy effect), so a 6 ms frame took 30 ms.
   Fix: scalar-float RK4 (identical results, 15x faster, `physics._integrate_at`), and for dense
   (240 fps) tracks integration on a 1/60 s grid with cubic Hermite read-out (max difference to the
   fine integration 5e-7 in; fitted v0 differs by < 4e-6 in/s, k by < 1e-4 relative).
   Standalone fit cost on the real tracks: with the scalar RK4 alone 97 ms (240 fps) / 67 ms (60 fps);
   with the coarse grid and 1/60 s steps 26 ms / 24 ms (the 150-280 ms above were measured while the
   other threads competed for the GIL).
2. **`_write_clips` copied up to 300 frames (100+ MB) while holding `Pipeline._lock`**, which every
   camera thread takes once per frame. Fix: take references under the lock, pin the ring so its
   buffers are not recycled while a clip is written, write the two cameras' clips in parallel
   threads (VideoWriter.write releases the GIL).
3. **Windows timer granularity**: with the default 15.6 ms tick `Event.wait(4 ms)` returns after
   16 ms, so a 240 fps file source was delivered in bursts of four frames. `Pipeline.start` now
   requests 1 ms (`timeBeginPeriod`) and a 0.5 ms GIL switch interval while it runs.
4. **Detector work on every frame**: colour conversion, thresholds and morphology now only run inside
   the bounding box of the motion mask (exact: identical detections); a frame without motion costs
   only the background model. The 480 px clip-ring copy uses INTER_LINEAR (0.1 ms instead of 0.35 ms)
   and the downscaled frame is a reusable buffer per camera (a fresh 0.7 MB array per frame cost
   page faults on every thread: measured 4x slower allocation than reuse with 6 threads).
5. Preview JPEG encoding runs in a helper thread per camera (only while a client is attached);
   capture queue depth is ~0.3 s of video (8-96 frames, <= 192 MB per camera) so a short stall
   cannot cost frames; camera/capture threads run above normal priority, reconstruction, tag and
   clip threads below normal (Windows); the offset search uses `offset_candidates` +
   `choose_offset_by_epipolar` (fixes the periodic-burst alias that locked in a wrong offset).
6. AprilTag id scans: at most 1 per second per camera on a <= 960 px wide copy (640 px lost the
   small HIVE tags of a 1080p test camera: `test_hive_tags_learn_and_follow_the_hive_state` failed).

Not the cause (tested): preview, clip ring, tag thread, BLAS threads (OPENBLAS/OMP_NUM_THREADS=1),
cv2 thread count, GIL switch interval alone, a busy sibling process.

## Limit that remains: sustained back-to-back load on this laptop

The cool-start numbers above are with 40 s idle before each run. Run back to back (7 s gap,
`round2_240_runs_a.txt`, measured before the last tweaks) the first synth_240 run drops 0 and the next
seven drop 17-20 %: the same process takes ~1.7x more CPU time in *every* thread (cam loop 1.7 s
-> 2.9 s CPU, capture 1.5 -> 3.0 s, detect_ms 1.3 -> 3.5; process CPU 14.6 s -> 26 s for the same
frames) while a single-threaded benchmark is only 8 % slower. That is the CPU slowing down under
multi-core load (power/thermal limit, E-core scheduling), not a pipeline wait: a 1 ms watchdog
thread sees almost no GIL stalls in those runs. Consequence: the two-camera 240 fps file stream
keeps ~4.4 cores busy on average (about half of it FFmpeg decode of the H.264 *fixtures*; real USB
cameras deliver MJPEG, which is lighter), so the 240 fps claim is verified for a rested machine
only. Re-measure synth_240 on the final hardware (and with the real cameras) before
promising it.

## Reproduce

    .venv\Scripts\python.exe evidence\m5_perf\rt_run.py synth_240           # drops, status.timing, shots vs truth
    .venv\Scripts\python.exe evidence\m5_perf\cool_runs.py <tree> LABEL out.txt synth_20 synth_240
    $env:HIVESHOT_PERF = "1"; .venv\Scripts\python.exe -m pytest tests\test_perf.py -k realtime -s

Other tools here: `rt_sample.py` (sampling profiler per thread), `rt_exp2/3/4.py` (per-frame and
per-phase timing), `rt_gil.py` (GIL/timer stall watchdog by phase), `rt_cpu2.py` + `thread_cpu.py`
(CPU seconds per native thread), `detect_equiv.py --save` on the old detector then `--check` on the
new one (frame-by-frame equality), `winperf.py` (EcoQoS/priority experiments; no effect).

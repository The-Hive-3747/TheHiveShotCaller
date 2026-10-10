# Per-frame stage timing (1080p, synth_basic cam0, single thread)

Method: `evidence/m5_perf/profile_before.py` (the pre-optimisation path, copied) and
`evidence/m5_perf/profile_after.py` (the real `ScaledDetector`, `Tracker2D` and
`Pipeline._after_frame` code) on the first 164 frames of `fixtures/synth_basic/cam0.mp4`
(1920x1080 at the time of measurement), `cv2.setNumThreads(1)`, `time.perf_counter()` around
each stage, preview JPEG forced every 4th frame (15 fps preview of a 60 fps source), clip
ring enabled. The machine was shared with 4 other agents, so absolute numbers carry
+-10 % noise; runs are listed in `before_after_runs.txt` and `after_runs_motion_scale.txt`.
Thread CPU time (`time.thread_time`) has 15.6 ms granularity on Windows and was not usable.

Mean ms per frame (preview is amortised over all frames):

| stage | before | after, shared downscale only (motion_scale 1.0) | after, default (motion_scale 0.5) |
|---|---|---|---|
| detect (resize + MOG2 + colour + contours) | 7.6 - 8.9 (typ. 8.4) | 7.8 - 8.3 | 4.25 - 4.56 |
| track (Tracker2D) | 0.13 | 0.12 | 0.12 |
| preview (resize, draw, JPEG; only with a client) | 0.60 - 0.70 | 0.41 - 0.47 | 0.41 |
| ring (480 px copy for clips) | 1.75 - 2.1 | 0.13 - 0.15 | 0.13 - 0.14 |
| **sum** | **10.1 - 11.9 (typ. 10.5)** | **8.5 - 9.0** | **4.9 - 5.25** (4.5 - 4.8 without a preview client) |

Target was < 5 ms per camera. Met with the default `detector.motion_scale = 0.5`
(4.9 / 4.9 / 5.25 under load, below 5 when idle; 11 ms budget at 90 fps leaves > 2x headroom).

What changed:
* The frame is shrunk once (INTER_AREA, process_scale 0.5) and the detector runs on that small
  frame; detections are mapped back to full-resolution pixels for the tracker.
* The 480 px clip ring frame is cut from the 960 px small frame (exact 2x area average, 0.13 ms
  instead of 1.5 ms from 1080p) into recycled buffers; the preview reuses the small frame
  (no resize at 960 px) and is only encoded while an MJPEG client is attached, at most at
  `preview_fps`.
* MOG2 (5 ms of the 8 ms detect cost) now runs on a half-size copy of the processed frame
  (`detector.motion_scale`, default 0.5; 1.0 restores the old behaviour). On both synthetic
  fixtures (synth_basic + synth_burst, 1006 frames) detections were identical frame by frame
  (same count on every frame, max centre shift 0.54 px full-res); see
  `experiment_motion_scale.txt`. Risk: real footage with small or blurred balls is not tested.

`tests/test_perf.py` asserts mean(detector + tracker) < 15 ms over 60 frames (single thread);
measured 5.4 ms (median 5.0 ms, max 8.3 ms) on an idle run and 10.65 ms during the heaviest
load before the motion-scale change.

Status exposes the live moving averages: `GET /api/pipeline/status` -> `timing`
(`detect_ms, track_ms, preview_ms, ring_ms, recon_ms, offset_s, offset_confidence`) and
`timing_per_camera`.

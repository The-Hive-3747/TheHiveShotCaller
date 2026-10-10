# Troubleshooting

Start with the console window: errors print there. Open `http://127.0.0.1:8765/api/pipeline/status` to see per-camera `fps`, `last_error`, `reconnects` and RTMP state.

## No camera found
Replug into a different USB port (use a direct USB 3 port on the PC rather than a shared hub where possible). Close other apps using the camera (Zoom, OBS, Camera app). Check Windows Settings > Privacy > Camera allows desktop apps. For capture cards, confirm the GoPro HDMI output is on (Media Mod connected, HDMI output enabled).

## Wrong device index
Open `http://127.0.0.1:8765/api/devices`: it lists index, resolution and fps for each camera found. Laptop webcams are usually index 0, so external cameras are 1 and 2. Set the index in Settings, Save, restart the pipeline. Indexes can change after replugging; re-check.

## Low fps
Compare `fps` in status with the target (60 or 90).
- Use a direct USB 3 port, not a shared hub.
- Set the camera to 1080p, not 4K.
- In dim light cameras lower frame rate to expose; add light and fix exposure.
- A GoPro recording to SD while streaming drops to 30 fps.
- Close extra browser tabs; set the Windows power plan to High performance.

## RTMP not connecting
- GoPro Quik: Live Stream > RTMP, URL `rtmp://<PC-IP>:1935/cam0` (camera B: `cam1`). Find the PC IP with `ipconfig`.
- PC and GoPro must be on the same network with no client isolation (a phone hotspot works).
- Allow the firewall prompt on Private networks.
- In status, `rtmp.available` false means `_internal\bin\mediamtx.exe` is missing (antivirus may have removed it). Restore it from the zip.
- Expect 2 to 4 s of latency.

## MediaMTX port busy
Port 1935 is used by another program (a leftover HiveShotTracker/mediamtx, or OBS). Find the owner with `netstat -ano | findstr :1935`, close it (end `mediamtx.exe` in Task Manager only if it is a leftover), then restart the pipeline. If the web port is busy, start with `--port 8766`.

## Calibration RMSE too high
- Intrinsics over 2 px: board not flat or not 1.00 in per square, motion blur, or the board never reached the frame corners. Re-record with more tilt and distance variety.
- Extrinsics over 2 px: usually one bad click (find the outlier in the per-point report and re-click it), points not spread across the image and heights, or field points not tape-measured.
- Camera moved since calibrating: redo extrinsics. Resolution, lens mode or zoom changed: redo intrinsics.

## Balls not detected
- Check the preview: the ball should show a drawn detection. Under 10 px means the camera is too far or the lens too wide.
- Lighting: no bright window behind the HIVE; even light on the ball.
- Tune color in the Settings tab, **Detector** section (OpenCV HSV, hue 0 to 179). Defaults: `pollen_hsv` [[15,100,100],[38,255,255]], `nectar_hsv` [[125,60,60],[170,255,255]]. If the ball is washed out, lower the saturation minimum; if background is detected, raise it or narrow the hue range.
- Check `min_radius_px` and `max_radius_px` against the ball size you see.

## Shots not finalizing
A shot finalizes about 0.75 s after the ball settles. It will not finalize if no session is running, the pipeline is stopped, or the ball is not tracked in both cameras (check both previews and the calibration). Balls less than 1.5 s apart merge into one burst; lower `burst_gap_s` only if your bursts are genuinely slower.

## Windows Firewall prompt
Shown the first time the web or RTMP server listens. Choose **Private networks** only. It matters for GoPro RTMP; HDMI and USB use do not need it. If dismissed, allow `HiveShotTracker.exe` and `_internal\bin\mediamtx.exe` under Windows Security > Firewall > Allow an app.

## Other
- Page will not load: confirm the console window is open and shows Uvicorn running; use http (not https) and `127.0.0.1`.
- SmartScreen warning on first run ("Windows protected your PC"): the exe is unsigned. Choose **More info**, then **Run anyway**. Antivirus may also flag or quarantine the exe or `_internal\bin\mediamtx.exe`; restore it or add an exception for the app folder.
- The exe does not start and a dialog or the console mentions `VCRUNTIME140`, `MSVCP140` or a missing DLL: unzip the *whole* zip (the runtime DLLs are in the `_internal` folder next to the exe); do not copy only the exe. If it still fails, install the Microsoft Visual C++ Redistributable (x64), then report it.
- Exit code 0, 1 or 3 when the app stops is normal. Closing the console window is the normal way to stop the app.
- Where is my data? `%LOCALAPPDATA%\HiveShotTracker\data` unless you started with `--data-dir` (see operator_guide.md section 8).

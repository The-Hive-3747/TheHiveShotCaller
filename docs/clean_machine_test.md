# Clean-machine test checklist

**Status of the requirement "the packaged build has been smoke-tested on a clean machine": NOT YET MET. It requires the owner to run this checklist.** All earlier checks ran on the development PC (same user profile, Python and VC++ runtime installed), so they do not count.

Run this on release candidates. Record results in the table at the end and keep screenshots.

## Test machine requirements
- A separate physical PC, or a fresh Windows 10/11 64-bit VM (snapshot it so the test can be repeated).
- **No Python, no Node.js, no Git, no source repository, no Visual C++ Redistributable** (check Settings > Apps: there should be no "Microsoft Visual C++ 2015-2022 Redistributable" entry). If the image already has it, uninstall it, or use another image; note which in the results.
- A **standard (non-administrator) user** account that has never run the app.
- Windows Defender / SmartScreen left at their default settings.
- Internet may be on, but the app must not need it.
- For the camera steps: a USB camera (or the real Option B cameras), plus a phone with the GoPro Quik app or a second PC with ffmpeg on the same Wi-Fi/LAN.

## Prepare
1. On the build PC, build the release (`build.ps1`) and note the zip name, size and SHA256 (`Get-FileHash`).
2. Copy **only the zip** to the test machine (USB stick or network share). Do not copy the repo, the venv, `dist\` folders or anything else.
3. Record: Windows version and build (`winver`), RAM, whether the VC++ redistributable is installed (should be "no"), and the user type (should be "standard").

## Steps and pass criteria
Tick each box, write the observation in the results table.

### A. Unzip and first launch
- [ ] Unzip to a normal folder as the non-admin user (for example `C:\HiveShotTracker` or `C:\Users\<user>\HiveShotTracker`). Confirm `HiveShotTracker\HiveShotTracker.exe`, `README.txt`, a `docs\` folder and an `_internal\` folder exist, and `README.txt` mentions SmartScreen and the data folder.
- [ ] Double-click `HiveShotTracker.exe`. **Expected:** SmartScreen "Windows protected your PC" appears (unsigned exe). Record exactly what it says. Click **More info** then **Run anyway**. If the machine blocks it outright (policy or antivirus), record the message; that is a finding.
- [ ] **Expected:** a console window opens and shows Uvicorn running. No error dialog about `VCRUNTIME140`, `MSVCP140`, `python312.dll` or any missing DLL. (An error here means the app-local runtime did not work: FAIL.)
- [ ] Windows Firewall prompt: choose **Private networks** only. Record whether the prompt appeared once or twice (app and mediamtx).
- [ ] Antivirus did not quarantine anything. Check Windows Security > Protection history.

### B. Demo run
- [ ] Open `http://127.0.0.1:8765` in a browser. Dashboard loads (header, tabs Dashboard / Shots / Replay / Calibration / Settings), pill shows `ws: connected`.
- [ ] Click **Pipeline start** (or start the exe with `--autostart`). Click **Start session**, type a name first.
- [ ] **Expected:** the built-in demo footage runs and the Shots tab reaches **6 shots, 4 made**. Take a screenshot.
- [ ] Replay tab: click a shot, the 3D view loads and **Play** animates the ball.
- [ ] Click **End session**, then **Export CSV**; the CSV opens and has one row per shot.

### C. Real USB camera
- [ ] Plug in the USB camera. Open `http://127.0.0.1:8765/api/devices` and confirm it is listed with a resolution and fps.
- [ ] Settings tab: set a source with kind `device`, target = that index, **Save config**, **Pipeline stop**, **Pipeline start**. **Expected:** the Cameras panel shows a live preview and a stable fps close to the camera's rate. Record the fps shown.
- [ ] Unplug the camera while running. **Expected:** the app does not crash; the status shows a camera error and recovers (reconnects) when replugged. Record what happens.

### D. RTMP publish (GoPro Quik app or ffmpeg)
- [ ] Find the test PC's IP (`ipconfig`). The phone/second PC must be on the same network (a phone hotspot is fine).
- [ ] Start the pipeline with an `rtmp` source, or look in `http://127.0.0.1:8765/api/pipeline/status` for the RTMP URLs. `rtmp.available` must be `true` (mediamtx started from the bundle).
- [ ] Publish to `rtmp://<PC-IP>:1935/cam0`:
  - GoPro Quik app: Live Stream > RTMP, enter the URL, start; **or**
  - ffmpeg on a second PC, for example: `ffmpeg -re -stream_loop -1 -i test.mp4 -c:v libx264 -preset veryfast -tune zerolatency -f flv rtmp://<PC-IP>:1935/cam0`
- [ ] **Expected:** the preview for that camera shows the incoming video within a few seconds (about 2 to 4 s latency) and fps is reported. Record the latency estimate and fps.
- [ ] Stop the publisher; the app shows the stream as lost and does not crash. Restart the publisher; it reconnects.

### E. Shutdown and cleanup
- [ ] Close the console window. **Expected:** the console closes. (The process exit code is 0, 1 or 3 and is not an error.)
- [ ] In Task Manager (Details tab) confirm **no** `HiveShotTracker.exe` and **no** `mediamtx.exe` remain. Verify port 1935 is free: `netstat -ano | findstr :1935` shows nothing.
- [ ] Relaunch the exe and open the dashboard. **Expected:** the earlier session and its shots are still listed (data persisted).

### F. Data location
- [ ] Open `%LOCALAPPDATA%\HiveShotTracker\data`. **Expected:** `hiveshot.db`, `config.json` and a `clips\` folder with files from the demo run (and `calibration.json` if you calibrated).
- [ ] Confirm nothing was written inside the unzipped app folder (compare folder size/time before and after, ignoring `__pycache__` if any).
- [ ] Run once with `--data-dir D:\hiveshot_test` (or any other writable folder); confirm data goes there instead.

### G. Cleanup test
- [ ] Delete the unzipped folder. Confirm the app is gone and the data folder remains. Unzip again to a different path and confirm the old data is picked up.

## Results (fill in)
| Item | Result (pass / fail / n/a) | Notes, screenshot filenames |
|---|---|---|
| Machine, Windows build, VC++ redist absent, standard user | | |
| Zip name, size, SHA256 | | |
| A. Unzip, SmartScreen, no missing-DLL error, firewall, antivirus | | |
| B. Demo run: 6 shots / 4 made, replay, CSV | | |
| C. Real USB camera: fps, unplug/replug | | |
| D. RTMP publish (Quik or ffmpeg): latency, fps, reconnect | | |
| E. Shutdown: no leftover processes, port 1935 free, data persists | | |
| F. Data location correct | | |
| G. Delete and re-unzip | | |

**Sign-off:** DoD 8 is met only when every row above is pass (or an n/a with a stated reason) on a machine that satisfies the requirements, with the date, tester and zip SHA256 recorded here. Until then it stays *not yet met*.

Tester: ____________  Date: ____________  Zip SHA256: ____________________________________

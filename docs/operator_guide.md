# Operator guide

Start here. The other guides are in the same `docs` folder: [camera_placement.md](camera_placement.md), [calibration.md](calibration.md), [troubleshooting.md](troubleshooting.md), [camera_bracket.md](camera_bracket.md), and [clean_machine_test.md](clean_machine_test.md) (checklist for verifying a new PC).

## 1. Install on a fresh PC
The packaged app is self-contained: **no Python, Node.js or other runtime needs to be installed**, and no internet is needed. The needed Visual C++ runtime DLLs are inside the folder.
1. Unzip `HiveShotTracker_<version>_win64.zip` to a normal folder (for example `C:\HiveShotTracker`). Keep the whole folder together. `README.txt` and `docs\` are next to the exe.
2. Double-click `HiveShotTracker\HiveShotTracker.exe`. The exe is not code-signed, so Windows SmartScreen may say "Windows protected your PC": click **More info**, then **Run anyway**. A console window opens and stays open while the app runs. If Windows Firewall asks, allow **Private networks** (needed only for GoPro RTMP; see troubleshooting.md).
3. Open a browser to **http://127.0.0.1:8765**. The dashboard loads.
4. To use another port or data folder: `HiveShotTracker.exe --port 8766 --data-dir D:\hiveshot_data --autostart`.
5. **Stop the app by closing the console window** (this is the normal way to stop it; Ctrl+C in the console also works). When the app is stopped from outside, Windows reports an exit code of 0, 1 or 3 (3 is the usual one for Ctrl+Break or a window close). Any of these is normal and not an error.

**Data folder (default):** `%LOCALAPPDATA%\HiveShotTracker\data`, usually `C:\Users\<you>\AppData\Local\HiveShotTracker\data`. It is created on first start and is never inside the unzipped folder, so you can delete or replace the app folder without losing data.

Without a camera configured, the built-in demo footage can be used to see the dashboard working. Start `HiveShotTracker.exe --demo` (or click **Run demo** in the top bar; **Exit demo** returns to your own setup). Demo mode runs two bundled synthetic videos, starts no RTMP server, and keeps its data in a separate `demo` subfolder of the data folder, so real sessions are never touched. (Without `--demo`, `--autostart` or **Pipeline start** also runs the basic demo footage when no camera is configured.)

## 2. Camera setup
Place and aim the cameras exactly as in [camera_placement.md](camera_placement.md) (tape marks, lens heights, pitch, settings, pre-session checklist).
- **Option A, GoPro.** Either HDMI to a capture card (appears as a camera device; use its device index in Settings) or RTMP over Wi-Fi: in the GoPro Quik app choose Live Stream > RTMP and set the URL to `rtmp://<PC-IP>:1935/cam0` for camera A and `.../cam1` for camera B. The app starts its own RTMP server (included in the zip); the status page lists the exact URLs. HyperSmooth off, Linear lens, 1080p60.
- **Option B, USB global shutter.** Plug each camera into its own USB 3 port on the PC if you can (two 1080p90 streams can starve a single shared hub link; see troubleshooting.md, "Low fps"). Pick the device index in Settings (see `/api/devices`), 1920x1080, 90 fps, fixed exposure.

In the **Settings** tab, under **Sources**, each camera is a row with `cam_id`, `kind` (`file`, `device`, `rtmp` or `url`), `target`, `width`, `height`, `fps_hint`, `realtime` and `loop`. For a USB or capture-card camera set `kind` to `device` and `target` to the device index; the **detected devices** drop-down plus the row's **use picked device** button fills it in. For RTMP set `kind` to `rtmp`. Click **Save config**, then **Pipeline stop** and **Pipeline start** so the new sources take effect. **Add source** adds a row; **remove** deletes one.

## 3. Calibration
Full detail is in [calibration.md](calibration.md). The short version, in the order the **Setup wizard** (opens on first run; **Setup** button in the top bar) walks you through it:

1. **Intrinsics (once per camera and lens setting).** Print the 1.00 in checkerboard (**Calibration** tab, or `http://127.0.0.1:8765/api/calib/checkerboard.pdf`) at 100 % scale, glue it flat to foam board, click **Start intrinsics**, move the board in front of the camera for about 20 s, click **Stop intrinsics**. Redo only when resolution, lens mode or zoom changes.
2. **Extrinsics with the tag kit (the normal way, both cameras at once).** Open `http://127.0.0.1:8765/api/calib/tags.pdf` and print it at 100 % scale: four letter-size pages, one AprilTag per page, each **6.00 in** square (check the printed line with a ruler). Cut the tags out leaving the white border, mount them flat on stiff card, and tape them to the HIVE frame where [calibration.md](calibration.md) section 3A shows (each page names its position). With both previews running and the tags in view, click **Auto-calibrate all**. Each camera card shows the tags it used, the reprojection error and `RMSE`. The tags can stay taped between sessions; press **Auto-calibrate all** again after every tripod move (about a minute in total).
3. **Check it.** The **Crosscheck** result is an *out-of-sample* test: it triangulates tags that the solve did **not** use (the field's own HIVE tags after a kit solve, or the kit tags after a HIVE-tags-only solve) and compares them with their known positions. Accept when reprojection is **under 2 px** per camera and the crosscheck **max error is within 1 in**. If the result says `out_of_sample: false` / "in-sample", no spare tag was visible, so the number only re-measures the points the solve used: make a HIVE tag or an unused kit tag visible to both cameras and run it again.
4. **Fallback: click the points by hand.** Use it when a tag cannot be taped on, is hidden, or Auto-calibrate reports an error you cannot fix. In the **Calibration** tab each camera card has **Refresh image**, **Undo point**, **Clear** and **Solve extrinsics**: click the listed field points on the image in the order shown on the right, then **Solve extrinsics**; the result line shows the error. Clicked points are accurate to about 1.5 px, so this method is looser than the kit.

The **Current calibration** box at the bottom shows what is saved; keep a copy of `calibration.json` after each good calibration. Budget under 10 minutes for a full re-calibration. A **calibration mismatch (n)** tag at the top means a camera is delivering a different image size than the one it was calibrated at (for example calibrated at 1920x1080, now sending 1280x720); hover over it for details, then fix the camera resolution or redo intrinsics.

**Field size.** In **Settings** set **field_size_in** to the real inside-wall-to-inside-wall distance of your field (measure wall to wall with a tape; the default is 144 in). It sets the field box in the 3D viewer and the geometry the API serves; it does not move the cameras.

## 4. Practice session, step by step
1. Open the dashboard and click **Pipeline start** (top bar). The **Cameras** panel on the left should show a live preview and the fps for each camera, and the tag at the top reads `pipeline: running`.
2. Set **Alliance** and **Up cell** (`audience` or `far`) to match the real HIVE, then click **Set HIVE state**. Update it whenever the HIVE tips.
3. Type a name in the session box and click **Start session**. (If you shoot without a session, shots are stored under "unassigned".)
4. Shoot. Each shot appears in the **Shots** tab a moment after the ball settles (about 0.75 s). Balls fired within 1.5 s of each other count as one burst.
5. Watch the counters on the **Dashboard** tab: Shots, Made, Bounce-out, Miss, Make rate, Tips, and the mean exit speed and launch angle.
6. Click **End session** when done. Past sessions stay available in the **Session** drop-down after a restart.

## 5. Reading the dashboard
- **Made**: the ball entered the up CELL opening and stayed in.
- **Bounce-out**: entered the opening, then left it. Not counted as made, but tracked separately because it points to exit speed or angle rather than aim.
- **Miss**: never entered the opening.
- **Failures by burst order** (chart): shots within the burst gap are numbered 1, 2, 3... in firing order, and the chart counts non-made shots at each position ("burst 1" = first ball, ..., "burst >4"). Red bars are all failures, amber bars are bounce-outs. A tall bar at 4 or more usually means the robot slows or jams late in a burst.
- **By ball type**: pollen versus nectar breakdown (table next to the chart).
- **Tip events**: collapsible list under the chart of HIVE tips and which shot caused them.
- **Shots tab** columns: `#`, Time, Burst (burst number and position in the burst), Ball, Result, **Exit m/s**, **Exit in/s**, **Angle** (launch elevation above horizontal, degrees), **Azimuth** (heading relative to the field axes, degrees), **Apex in** (highest point of the flight, inches above the floor). Use the **Result** filter (all, made, miss, bounce_out) to narrow the list. Exit speed is the ball speed leaving the robot, from the fitted 3D track; it is best with the optional exit-speed camera C or 120+ fps.
- **Equation and fit RMSE**: shown in the **Replay** tab's info box for the selected shot. The equation looks like `z = a s^2 + b s + c (in)`, the fitted height z against distance s along the shot plane. A large fit RMSE means a poor track; treat that shot's numbers with caution.

## 6. Replay
Click a row in the **Shots** tab; the **Replay** tab opens with the shot. The 3D viewer shows field, HIVE, robot and ball path (solid yellow is the measured track, dashed cyan the fitted parabola). Controls: **Play** (becomes **Pause**), the slider to scrub, the **Speed** drop-down (0.1, 0.25, 0.5, 1 x), and a **Follow ball** checkbox; drag to orbit, wheel to zoom. Shots with a saved clip show a **clip** link to the camera video.

## 7. Export
Select a session in the **Session** drop-down, then click **Export CSV** in the top bar, or open `http://127.0.0.1:8765/api/sessions/<id>/export.csv`. One row per shot with result, exit speed, angles, apex and equation. Opens in Excel.

## 8. Data location and backups
Everything lives in the data folder. By default that is `%LOCALAPPDATA%\HiveShotTracker\data` (see section 1); `--data-dir` overrides it (recommended if several people share the PC or you want it on another drive).
- `hiveshot.db`: sessions and shots
- `config.json`: settings (the **Settings** tab writes here); `calibration.json`: camera calibration
- `clips\`: saved shot video

Back up by closing the app and copying the whole data folder. Restore by copying it back. Copy `calibration.json` after every good calibration; it is the hardest thing to recreate. Uninstalling is just deleting the unzipped folder; delete the data folder too only if you want to discard your data.

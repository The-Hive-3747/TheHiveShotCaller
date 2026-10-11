# TheHiveShotCaller

Shot analytics for the FTC BIOBUZZ HIVE, built by FTC Team 3747 The Hive.

Point two inexpensive USB cameras at the HIVE on your practice field and the app tells you, for every ball your robot launches:

- whether it was **made**, **missed**, or **bounced out**
- its **exit speed**, **launch angle**, and the **fitted trajectory equation**
- where it fell in the burst, so you can see whether ball 1, 2, 3 or 4 is the one that fails
- a **3D replay** of the shot with the field, the HIVE and your robot

Session statistics (make rate, failure order histogram, per ball type) update live and export to CSV. HIVE tips are logged automatically.

## What you need

- A Windows PC (the app is a single download, no Python or other runtime required)
- Two USB global-shutter cameras at 1080p 90 fps, two 16 ft USB extension cables, and two 60 in tripods. The exact parts we use are in [PURCHASE_LIST.md](PURCHASE_LIST.md), about 370 USD total.
- A 3D printer for the camera bracket ([docs/camera_bracket.stl](docs/camera_bracket.stl)), or any bracket with a 1/4-20 tripod nut
- A printer for the four-page AprilTag calibration sheet and the checkerboard lens target (the app generates both)

GoPro or capture-card setups also work: any camera the PC can open, and RTMP streams, are accepted as sources.

## Try it without any hardware

Download the latest release zip, unzip it anywhere, and run:

```
HiveShotTracker.exe --demo
```

Your browser opens at http://127.0.0.1:8765 with a demo session running on bundled synthetic video. Everything in the interface works in demo mode.

## Setting up on a field

1. Run `HiveShotTracker.exe`. The setup wizard opens on first run.
2. Plug the cameras into separate USB ports on the PC and let the wizard detect them.
3. Place the tripods where the placement map says ([docs/camera_placement.md](docs/camera_placement.md)) and tape the feet so you can put them back next time.
4. Print the checkerboard and wave it in front of each camera for 20 seconds (the Lens step) so the app learns each lens.
5. Print the AprilTag sheet and place the four tags where the wizard shows: two lie on the slanted logo panel of the HIVE frame, two stand at the frame's base corners on the audience side. Press **Auto-calibrate**. The HIVE's own tags are used as a cross-check and to read which CELL is up.
6. Click a ball in each preview so the app learns your ball colors.
7. Start a session and shoot.

The whole setup takes about 15 minutes the first time and a couple of minutes after that. Full details are in the [operator guide](docs/operator_guide.md) and [troubleshooting](docs/troubleshooting.md).

## How it works

Each camera's frames are searched for balls by color and motion. The two cameras are calibrated against the HIVE geometry taken from the official field CAD, so each ball's path is reconstructed in field coordinates and tested against the real CELL opening. A gravity-plus-drag fit on the path gives the exit speed and angle; the parabola you see in the replay is the fit through the measured points.

## Running from source

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]
powershell -ExecutionPolicy Bypass -File tools\fetch_deps.ps1
.venv\Scripts\python -m hiveshot.app --demo
```

Tests: `.\test.ps1`. API contract for the browser UI: [docs/api.md](docs/api.md).

## License and credits

Field geometry is taken from the FIRST Tech Challenge BIOBUZZ Competition Manual and field CAD. Bundled third-party software: [three.js](https://threejs.org) (MIT) and [MediaMTX](https://github.com/bluenviron/mediamtx) (MIT).

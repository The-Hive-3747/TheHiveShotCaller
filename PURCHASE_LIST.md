# HiveShotTracker — Definitive purchase list and delivery plan

Decision (lead, 2026-10-10): build on two USB global-shutter cameras plugged directly into the PC. No GoPros, no capture cards, no hub. This is the cheapest setup that meets the accuracy targets, and the software already treats every camera as a generic video source, so nothing changes in code if cameras are swapped later.

Prices are Amazon US list prices seen on 2026-10-10 and may move. Quantities are what you need, nothing assumed on hand except the PC, a tape measure, and a printer.

## Buy now (one order)

| # | Item | Qty | Link | Unit USD | Line USD | Why |
|---|---|---|---|---|---|---|
| 1 | Arducam 2.3 MP USB camera, global shutter, 110° lens, 1080p at 90 fps, USB 2.0 (5 V, 1.2 W, ~240 mA; board 34 x 34 mm) | 2 | https://www.amazon.com/dp/B0FLX2DSSS | 99.99 | 199.98 | The two tracking cameras. Global shutter and 90 fps are what make the speed and arc numbers trustworthy. |
| 2 | Tripp Lite USB 3.0 active extension cable, 16 ft (U330-05M), 770 mA to the device, USB 2.0 backward compatible | 2 | https://www.amazon.com/Tripp-Lite-SuperSpeed-Extension-U330-05M/dp/B008VOPDOU | ~35 | ~70 | Camera cables are 1 m. Each camera gets its own run back to the PC. The USB 2.0 U026-016 was rejected on 2026-10-10: it supplies only 150 mA, below the camera's 240 mA draw. |
| 3 | UBeesize MT60 60 in tripod | 2 | https://www.amazon.com/UBeesize-MT60-Aluminum-Lightweight-Professional/dp/B07NQJ4BDS | ~35 | ~70 | One per camera, 1/4-20 screw head. |
| 4 | Bracket hardware for the 3D-printed mount: M2 x 12 mm screws with nuts (assorted pack; 10 mm minimum to pass board, standoff and plate), 1/4-20 hex nuts (x2) | 1 set | https://www.amazon.com/s?k=m2+screws+nuts+assortment ; any hardware store for 1/4-20 nuts | ~10 | ~10 | The bracket itself is printed on your Bambu X1C from docs/camera_bracket.stl (supplied). Four M2 screws hold the board, the 1/4-20 nut drops into the base pocket for the tripod screw. |
| 5 | USB-C to USB-A adapter, 2-pack | 1 | https://www.amazon.com/s?k=usb+c+to+usb+a+adapter+2+pack | ~8 | ~8 | Only needed if the PC has fewer than two free USB-A ports. Cheap insurance. |
| 6 | Foam board 20 x 30 in, white | 1 | any office or craft store | ~5 | ~5 | Backing for the printed checkerboard calibration target (PDF supplied by the app, print at 100%); offcuts also stiffen the four printed 6 in kit tags. |
| 7 | Painter's tape | 1 | any | ~5 | ~5 | Mark tripod feet positions on the floor. |
| | **Total** | | | | **~370** | |

## Do not buy

- GoPro, Media Mod, capture cards: not needed with USB cameras. Live GoPro output is 30 to 60 fps and would give worse numbers at three times the cost.
- Powered USB hub: both cameras go straight into the PC on separate ports. Two 1080p90 MJPEG streams would starve on one shared USB 2.0 hub link.
- The Arducam ABS case previously listed: it fits 25 x 24 mm boards, not this 34 x 34 mm board.
- Third camera: optional later. The two-camera setup already gives a 105° triangulation angle (docs/camera_placement.md). Add a third only if real footage shows the CELL entry is often occluded.

## Setup plan after the parts arrive

| Step | What | Time | Done when |
|---|---|---|---|
| 1 | Unzip the app build, run it, open http://127.0.0.1:8765 | 10 min | Dashboard loads with the built-in demo video |
| 2 | Plug cameras in (separate PC ports), Settings tab: pick device indexes, set 1920x1080, 90 fps, MJPG | 15 min | Both previews show LIVE at 85 to 90 fps, dropped 0 |
| 3 | Place tripods per docs/camera_placement.md (cam A = `cam0`: lens plumb spot 4.5 in outside the -X wall and 8.5 in along it from the +Y wall's outer edge, i.e. (-78, +65) from field center, lens 30 in high; cam B = `cam1`: 4.5 in outside the +Y wall and 8.5 in from the +X wall's outer edge, i.e. (+65, +78), lens 20 in high), aim with the floor-cross method in that document, tape the feet | 20 min | Up CELL and launch area visible in both previews |
| 4 | Print the checkerboard PDF at 100%, glue to foam board, record 20 s per camera in the Calibration tab (intrinsics) | 15 min | Reprojection RMSE under 2 px per camera |
| 5 | Print the 4-page tag kit (`/api/calib/tags.pdf`, 6 in tags, 100% scale), tape the tags where docs/calibration.md section 3A says, press **Auto-calibrate all** in the Setup wizard or Calibration tab. Fallback if a tag cannot be placed: click the 8 reference points per camera (docs/calibration.md section 3B) | 10 min | Crosscheck on held-out tags within 1 in; status shows no calibration mismatch |
| 6 | Shoot 10 balls by hand or with the robot; check detections, tune the POLLEN/NECTAR color ranges in Settings if balls are missed | 30 min | Recall above 95 percent on the live preview |
| 7 | Run a 20-shot session, export CSV, open replays | 20 min | Definition of Done items 2 and 4 verified on real hardware |

Total first-day setup: about 2 hours.

## Sources for prices
- Arducam listing: https://www.amazon.com/dp/B0FLX2DSSS, 99.99 USD confirmed by the owner's purchasing check on 2026-10-10
- Tripp Lite U330-05M: https://www.amazon.com/Tripp-Lite-SuperSpeed-Extension-U330-05M/dp/B008VOPDOU
- UBeesize MT60: https://www.amazon.com/UBeesize-MT60-Aluminum-Lightweight-Professional/dp/B07NQJ4BDS

## Order status (2026-10-10, from the owner's purchasing agent)

Confirmed order, going into the team's Amazon cart on 2026-10-10 evening:

| Item | Qty | Line USD |
|---|---|---|
| Arducam B0FLX2DSSS | 2 | 199.98 |
| Tripp Lite U330-05M (B008VOPDOU), two sellers | 2 | 79.26 |
| UBeesize MT60 (B07NQJ4BDS) | 2 | 77.98 |
| Mywish M2 stainless kit (B0CTJY6G5K), includes M2x12 | 1 | 9.99 |
| Bates 1/4-20 hex nuts, 50 pack (B0CJ9FFH2Y) | 1 | 4.99 |
| UCreate foam board 20x30, 10 sheets (B074QZMLQF) | 1 | 31.42 |
| ScotchBlue painter's tape 1.88 in | 1 | 7.79 |
| **Total before tax** | | **411.41** |

- No hub, no board case, no GoPro items, no USB-C adapter: the team already has USB-C hubs with USB-A ports. Plan: one hub per camera on separate USB-C ports (the PC has two USB host controllers), or cameras straight into USB-A ports.
- ETA: most items 2026-10-11 to 10-15; the second extension cable about 2026-10-20. Setup can start with the first cable and the second camera on its 1 m cable next to the PC.

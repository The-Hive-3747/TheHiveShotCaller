# HiveShotTracker — Definitive purchase list and delivery plan

Decision (lead, 2026-10-10): build on two USB global-shutter cameras plugged directly into the PC. No GoPros, no capture cards, no hub. This is the cheapest setup that meets the accuracy targets, and the software already treats every camera as a generic video source, so nothing changes in code if cameras are swapped later.

Prices were checked on 2026-10-12 (Amazon.com product pages and Home Depot store 21st South, Salt Lake City) and may move. Quantities are what you need, nothing assumed on hand except the PC, a tape measure, and a printer.

## Buy now (one order)

| # | Item | Qty | Link | Unit USD | Line USD | Why |
|---|---|---|---|---|---|---|
| 1 | Arducam 2.3 MP USB camera, global shutter, 110° lens, 1080p at 90 fps, USB 2.0 (5 V, 1.2 W, ~240 mA; board 34 x 34 mm) | 2 | https://www.amazon.com/dp/B0FLX2DSSS | 99.99 | 199.98 | The two tracking cameras. Global shutter and 90 fps are what make the speed and arc numbers trustworthy. In stock 2026-10-12. |
| 2 | Tripp Lite USB 3.0 active extension cable, 16 ft (U330-05M), 770 mA to the device, USB 2.0 backward compatible | 2 | https://www.amazon.com/dp/B008VOPDOU | 40.21 | 80.42 | Camera cables are 1 m. Each camera gets its own run back to the PC. The USB 2.0 U026-016 was rejected on 2026-10-10: it supplies only 150 mA, below the camera's 240 mA draw. Amazon showed "only 2 left" on 2026-10-12; 35 other sellers from 39.91. |
| 3 | Amazon Basics 50 in lightweight tripod, 16.1 to 50 in, 3-way head with bubble level, 1/4-20 screw | 2 | https://www.amazon.com/dp/B00XI87KV8 | 16.99 | 33.98 | One per camera. The placement plan needs lens heights of only 36 in (camera A) and 20 in (camera B); a 60 in tripod is needed only for the optional third camera (58 in). Replaces the UBeesize MT60 (B07NQJ4BDS), unavailable since 2026-10-12 and with a 19 in minimum that barely reached camera B's height anyway. Measure the leg radius at 20 in and 36 in when it arrives (docs/camera_placement.md section 2 assumes about 20 in). |
| 4 | M2 screw and nut kit (must include M2 x 12 screws and M2 nuts; 8 of each are used) | 1 | https://www.amazon.com/dp/B0GCHWGXNS (981 pc stainless, 3.99) or the Mywish kit https://www.amazon.com/dp/B0CTJY6G5K (9.99) | 3.99 | 3.99 | Four M2 x 12 screws and nuts hold each camera board to the printed bracket (docs/camera_bracket.md: 10 mm minimum, 12 mm preferred). No local store carries M2 x 12 in small packs, so a kit is the cheapest route. The 3.99 kit was found by price sort and not vetted; check reviews or use the Mywish kit. |
| 5 | 1/4-20 hex nut, zinc | 2 | Home Depot Everbilt 1/4-20 hex nut, 0.14 each (model 801736) or 10-pack 1.57 (model 825831); any hardware store | 0.14 | 0.28 | One drops into the base pocket of each printed bracket for the tripod screw. A standard 7/16 in across-flats nut fits the 11.2 mm pocket. Replaces the 50-pack (B0CJ9FFH2Y, 4.99). |
| 6 | Foam board 20 x 30 in, white, 3/16 in | 1 to 2 | Walmart Pen+Gear single sheet https://www.walmart.com/ip/5347546821 (1.92); Dollar Tree usually 1.25 | 1.92 | 3.84 | Backing for the printed checkerboard calibration target (PDF supplied by the app, print at 100%); offcuts stiffen the four printed 6 in kit tags. One sheet does the job; two gives a spare. Replaces the 10-sheet pack (B074QZMLQF, 31.42). If you want it in the same Amazon order, UCreate 22 x 28 in 5-pack is 22.33 (B00IWSHEB0). |
| 7 | Painter's tape, 1.88 in x 60 yd | 1 | FrogTape green https://www.amazon.com/dp/B002YCGNXA (7.21) or ScotchBlue https://www.amazon.com/dp/B00004Z4DU (7.79); any brand or a roll from the shop | 7.21 | 7.21 | Mark tripod feet positions on the floor and tape cables down. Low-tack so it peels cleanly from the tiles and glass wall. |
| | **Total** | | | | **~330** | Down from ~411 in the 2026-10-10 cart (tripods, hardware and foam board swapped). |

## Do not buy

- GoPro, Media Mod, capture cards: not needed with USB cameras. Live GoPro output is 30 to 60 fps and would give worse numbers at three times the cost.
- Powered USB hub: both cameras go straight into the PC on separate ports. Two 1080p90 MJPEG streams would starve on one shared USB 2.0 hub link.
- The Arducam ABS case previously listed: it fits 25 x 24 mm boards, not this 34 x 34 mm board.
- Third camera: optional later. The two-camera setup already gives a good triangulation angle (see docs/camera_placement.md for the current number). Add a third only if real footage shows the CELL entry is often occluded.

## Setup plan after the parts arrive

| Step | What | Time | Done when |
|---|---|---|---|
| 1 | Unzip the app build, run it, open http://127.0.0.1:8765 | 10 min | Dashboard loads with the built-in demo video |
| 2 | Plug cameras in (separate PC ports), Settings tab: pick device indexes, set 1920x1080, 90 fps, MJPG | 15 min | Both previews show LIVE at 85 to 90 fps, dropped 0 |
| 3 | Place tripods exactly where docs/camera_placement.md and its map say. Positions, lens heights, aims and tape distances are generated by the optimizer and change whenever the field model changes, so that document is the only source of truth; this list does not repeat the numbers. Tape the feet. | 20 min | Up CELL and launch area visible in both previews; both cameras read the kit tags |
| 4 | Print the checkerboard PDF at 100%, glue to foam board, record 20 s per camera in the Calibration tab (intrinsics) | 15 min | Reprojection RMSE under 2 px per camera |
| 5 | Print the 4-page tag kit (`/api/calib/tags.pdf`, 6 in tags, 100% scale), tape the tags where docs/calibration.md section 3A says, press **Auto-calibrate all** in the Setup wizard or Calibration tab. Fallback if a tag cannot be placed: click the 8 reference points per camera (docs/calibration.md section 3B) | 10 min | Crosscheck on held-out tags within 1 in; status shows no calibration mismatch |
| 6 | Shoot 10 balls by hand or with the robot; check detections, tune the POLLEN/NECTAR color ranges in Settings if balls are missed | 30 min | Recall above 95 percent on the live preview |
| 7 | Run a 20-shot session, export CSV, open replays | 20 min | Definition of Done items 2 and 4 verified on real hardware |

Total first-day setup: about 2 hours.

## Sources for prices (checked 2026-10-12)
- Arducam: https://www.amazon.com/dp/B0FLX2DSSS, 99.99, in stock
- Tripp Lite U330-05M: https://www.amazon.com/dp/B008VOPDOU, 40.21 (Amazon, 2 left), other sellers from 39.91
- Amazon Basics 50 in tripod: https://www.amazon.com/dp/B00XI87KV8, 16.99, in stock; 60 in version 32.99 if a third camera is added
- UBeesize MT60: https://www.amazon.com/dp/B07NQJ4BDS, "currently unavailable", min height 48 cm (19 in)
- M2 kit: https://www.amazon.com/dp/B0GCHWGXNS, 3.99; Mywish https://www.amazon.com/dp/B0CTJY6G5K, 9.99
- 1/4-20 nuts: Home Depot Everbilt 801736 (0.14 each), 825831 (10-pack 1.57); M2 x 12 screws and M2 nuts are not stocked there in small packs
- Foam board: Walmart Pen+Gear 20 x 30 https://www.walmart.com/ip/5347546821, 1.92; UCreate 22 x 28 5-pack https://www.amazon.com/dp/B00IWSHEB0, 22.33
- Tape: FrogTape https://www.amazon.com/dp/B002YCGNXA, 7.21; ScotchBlue https://www.amazon.com/dp/B00004Z4DU, 7.79

## Order status (2026-10-10, from the owner's purchasing agent)

Cart as built on 2026-10-10 evening, before the 2026-10-12 substitutions above (tripods, hardware, foam board, tape). Anything from this cart that did not ship should be ordered from the Buy now table instead.

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

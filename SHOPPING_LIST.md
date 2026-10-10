# HiveShotTracker — Purchase List (2026-10-10)

Prices change; check each listing before ordering. Links are Amazon.com product pages found on 2026-10-10.

## Required

| # | Item | Qty | Link | Notes |
|---|---|---|---|---|
| 1 | GoPro HERO13 Black | 2 | https://www.amazon.com/GoPro-HERO13-Black-Compatability-HB/dp/B0DCM34GXX | Body-only listing. A HERO12 Black works identically for this project if cheaper. |
| 2 | GoPro Media Mod (HERO13/12/11/10/9) official | 2 | https://www.amazon.com/GoPro-HERO13-HERO12-HERO11-HERO10/dp/B08FRSB1CM | Needed for the micro-HDMI output. Buy the official one; third-party "Media Mod frames" have no HDMI port. Listing sometimes shows unavailable; GoPro.com also sells it. |
| 3 | Elgato Cam Link 4K | 2 | https://www.amazon.com/Elgato-Cam-Link-Broadcast-Camcorder/dp/B07K3FN5MR | One per GoPro. Avoid the cheap clones in the same search results. |
| 4 | Micro-HDMI to HDMI cable, 10 ft | 2 | https://www.amazon.com/BlueRigger-Speed-MicroBlueRigger-Micro-Ethernet/dp/B00609B3J2 | Media Mod to Cam Link. 10 ft reaches a tripod outside the field wall. |
| 5 | Third camera: Arducam 2.3MP global shutter color USB, 1080p at 90 fps | 1 | https://www.amazon.com/clp/B0FLX2DSSS | Exit-speed and CELL-entry camera. Color, global shutter, USB 2.0, no drivers. Alternatives: Arducam 1MP OV9782 color at 100 fps https://www.amazon.com/Arducam-Shutter-Distortion-Without-Microphones/dp/B0CLXZ29F9 or Arducam OV9281 monochrome at 120 fps https://www.amazon.com/Arducam-Shutter-Android-Devices-Raspberry/dp/B0FXWWF55X |
| 6 | USB 3.0 active extension cable, 16 ft | 1 | https://www.amazon.com/Tripp-Lite-SuperSpeed-Extension-U330-05M/dp/B008VOPDOU | The Arducam ships with a 1 m cable; this reaches the tripod behind the robot. |
| 7 | Tripods, 60 in | 3 | https://www.amazon.com/UBeesize-MT60-Aluminum-Lightweight-Professional/dp/B07NQJ4BDS | One per camera. Any 60 in tripod with a 1/4-20 screw works. |
| 8 | GoPro folding-fingers to 1/4-20 tripod adapter | 2 | https://www.amazon.com/Folding-Fingers-Compatible-Replacement-Connector/dp/B0C55R2ZZ5 | Mounts the GoPro (in its Media Mod) to a tripod screw. |
| 9 | microSD card, SanDisk Extreme 128 GB V30 A2 | 2 | https://www.amazon.com/SanDisk-128GB-Extreme-microSD-Adapter/dp/B07FCMKK5X | For 1080p240 recording used by the post-match high-speed analysis mode. |
| 10 | Powered USB 3.0 hub, 7 port | 1 | https://www.amazon.com/Anker-7-Port-Adapter-Charging-iPhone/dp/B014ZQ07NE | Two Cam Links plus the Arducam and the extension cable exceed most PCs' free USB ports. Plug each Cam Link into a different root port where possible. |
| 11 | USB-C power for GoPros: 10 ft USB-C to USB-C cables, 2-pack | 1 | https://www.amazon.com/Anker-2-Pack-Charging-MacBook-Galaxy/dp/B0CCRNJ7Y4 | GoPro batteries last about an hour with HDMI out. The Media Mod passes power through its USB-C port. Pair with any 20 W or better USB-C wall charger, 2 ports: https://www.amazon.com/clp/B0DBV42QQN |

## Optional

| Item | Qty | Link | Notes |
|---|---|---|---|
| Small camera case or bracket for the Arducam board | 1 | https://www.amazon.com/Arducam-Raspberry-Autofocus-Compatible-Official/dp/B09TNG4V55 | The Arducam is a bare board. This 25 x 24 mm ABS case has a 1/4-20 hole; confirm the board footprint on the listing, otherwise a 3D-printed bracket or a piece of angle aluminum with a 1/4-20 nut works. |
| Checkerboard calibration target | 1 | https://www.amazon.com/Checkerboard-Calibration-Anti-Glare-Diffuse-Reflection/dp/B0G3VCJXT9 | A printed 9 x 6 inner-corner checkerboard glued flat to foam board is free and good enough. I will supply the PDF. |
| Painter's tape | 1 | any | Mark tripod foot positions on the floor so calibration survives between sessions. |

## Not needed

- No RTMP hardware. Wireless streaming uses the GoPro Quik app on a phone and a free local RTMP server bundled with the application.
- No GPU purchase. The pipeline is sized for CPU on this PC; if sustained real-time proves short, that is a later decision.

## Cost estimate (US retail, 2026-10-10, before tax and shipping)

Amazon does not expose prices to automated lookup, so these are ranges from retailer listings and recent price history. Verify on the live pages.

| Item | Qty | Unit (USD) | Line (USD) |
|---|---|---|---|
| GoPro HERO13 Black | 2 | 350–430 | 700–860 |
| GoPro Media Mod | 2 | 80 | 160 |
| Elgato Cam Link 4K | 2 | 80–130 | 160–260 |
| Micro-HDMI to HDMI 10 ft | 2 | 10 | 20 |
| Arducam 2.3 MP global shutter USB (USB 2.0 board) | 1 | 70–100 | 70–100 |
| USB 3.0 active extension 16 ft | 1 | 30–40 | 30–40 |
| Tripod 60 in | 3 | 30–40 | 90–120 |
| GoPro 1/4-20 adapter | 2 | 10 | 20 |
| microSD 128 GB | 2 | 15–20 | 30–40 |
| Powered USB 3.0 hub | 1 | 40–50 | 40–50 |
| USB-C cables 2-pack + 2-port chargers 2-pack | 1 | 30 | 30 |
| **Required total** | | | **1,350–1,700** |
| Optional: Arducam case, checkerboard target, tape | | | 20–40 |

Cheaper variants:
- HERO12 Black instead of HERO13 saves roughly 50–100 per camera with no loss for this project.
- Skip the third camera, extension and one tripod (about 190–260) if you accept exit-speed accuracy of roughly 10–15 percent from the GoPros alone. It can be added later without changing the software.
- Generic USB 3.0 HDMI capture dongles run 15–25 each versus Cam Link's 80–130, but drop frames more often. Not recommended for the primary feeds.

## Minimum-but-good setups (2026-10-10)

### Option A — GoPro path, trimmed (matches the original spec)

| Item | Qty | Unit (USD, approx) | Line | Link |
|---|---|---|---|---|
| GoPro HERO12 Black (HERO13 if same price) | 2 | 300–350 | 600–700 | https://www.amazon.com/s?k=gopro+hero12+black |
| GoPro Media Mod, official | 2 | 80–100 | 160–200 | https://www.amazon.com/GoPro-HERO13-HERO12-HERO11-HERO10/dp/B08FRSB1CM |
| Elgato Cam Link 4K | 2 | 80–100 | 160–200 | https://www.amazon.com/Elgato-Cam-Link-Broadcast-Camcorder/dp/B07K3FN5MR |
| Micro-HDMI to HDMI 10 ft | 2 | 10 | 20 | https://www.amazon.com/BlueRigger-Speed-MicroBlueRigger-Micro-Ethernet/dp/B00609B3J2 |
| Tripod 60 in | 2 | 30–35 | 60–70 | https://www.amazon.com/UBeesize-MT60-Aluminum-Lightweight-Professional/dp/B07NQJ4BDS |
| GoPro 1/4-20 tripod adapter | 2 | 10 | 20 | https://www.amazon.com/Folding-Fingers-Compatible-Replacement-Connector/dp/B0C55R2ZZ5 |
| microSD 128 GB | 2 | 15 | 30 | https://www.amazon.com/SanDisk-128GB-Extreme-microSD-Adapter/dp/B07FCMKK5X |
| **Total** | | | **1,050–1,240** | |

Live feeds at 1080p60. Exit speed roughly ±10–15 percent live; ±5 percent from 240 fps SD-card files analyzed after the session. No third camera.

### Option B — USB global-shutter path (recommended for budget and accuracy)

| Item | Qty | Unit (USD, approx) | Line | Link |
|---|---|---|---|---|
| Arducam 2.3 MP global shutter color USB, 1080p at 90 fps | 2 | 80–110 | 160–220 | https://www.amazon.com/clp/B0FLX2DSSS |
| USB 3.0 active extension 16 ft | 2 | 30–40 | 60–80 | https://www.amazon.com/Tripp-Lite-SuperSpeed-Extension-U330-05M/dp/B008VOPDOU |
| Tripod 60 in | 2 | 30–35 | 60–70 | https://www.amazon.com/UBeesize-MT60-Aluminum-Lightweight-Professional/dp/B07NQJ4BDS |
| Camera board case with 1/4-20 hole (or DIY bracket) | 2 | 10 | 20 | https://www.amazon.com/Arducam-Raspberry-Autofocus-Compatible-Official/dp/B09TNG4V55 |
| Powered USB 3.0 hub | 1 | 40–50 | 40–50 | https://www.amazon.com/Anker-7-Port-Adapter-Charging-iPhone/dp/B014ZQ07NE |
| **Total** | | | **340–440** | |

Live feeds at 1080p90 with global shutter, which is better for ball tracking than either GoPro mode. No HDMI, no capture cards, no batteries, no stream latency. Exit speed roughly ±5 percent live. A third camera later adds about 150. Downsides: not waterproof, no on-camera recording, and the Amazon price for the Arducam was not verifiable by automated lookup (a Newegg listing showed 162; check the Amazon page before ordering).

Either option can be upgraded to the full list later without software changes; the application treats every camera as a generic video source.

## Purchase-check corrections (2026-10-10, from the owner's purchasing review)

- **Drop the Arducam board case.** The linked case fits 25 x 24 mm boards; the Arducam 2.3 MP board is 34 x 34 mm. Mount the bare board with a small L-bracket (aluminum angle, two M2 screws through the board's corner holes, a 1/4-20 nut epoxied to the bracket) or a 3D-printed bracket. A fitting case can be chosen later.
- **USB bandwidth.** The Arducam is USB 2.0. Two 1080p90 MJPEG streams need roughly 120 to 180 Mbps each, which does not fit reliably on one shared USB 2.0 hub link (about 300 Mbps usable). Plug each camera into a separate USB port directly on the PC (this PC has two separate USB host controllers), not both into the same hub. The powered hub is then only needed for the third camera or other accessories, and can be skipped for Option B. The app's camera overlay shows measured fps and dropped frames, so bandwidth starvation is visible immediately.
- **Extension cables.** Because the cameras are USB 2.0, a USB 2.0 active extension (16 ft, about 12 to 20 USD) works and is cheaper than the USB 3.0 version. Either is fine. Buying the second cable from a different seller at about 40 USD is acceptable but not necessary.

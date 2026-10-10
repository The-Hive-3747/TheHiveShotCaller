# Camera tripod bracket

A 3D-printable L-bracket that holds a bare Arducam 2.3 MP global-shutter USB 2.0 board
(34 x 34 mm, M12 lens) on a standard 1/4-20 tripod head. The tripod head provides tilt, so
the bracket itself is a fixed 90 degrees.

Files: `docs/camera_bracket.stl` (binary, mm), `docs/camera_bracket.png` (front / side / top /
isometric views). Source: `tools/make_bracket.py` (parametric; regenerate with
`.venv\Scripts\python.exe tools\make_bracket.py`).

## Dimensions (mm)

| Feature | Value |
|---|---|
| Overall | 44 wide x 47 deep x 50 tall (44 + 3 mm standoff bosses deep) |
| Vertical plate | 44 x 4 thick x 50 tall (board mounts to its front, -Y, face) |
| Base plate | 44 x 40 x 7 thick (7 rather than 6 so the nut pocket keeps a 1.2 mm ledge) |
| Gussets | one each side, 4 mm thick, 22 mm legs |
| Lens clearance hole | 20 mm dia, centred on the board centre |
| Board mounting | 4 radial slots, 2.4 mm wide, ~6.6 mm long, centred on a 29 mm pitch; fit hole pitch 26-32 mm |
| Standoffs | 5 mm wide, 3 mm tall bosses around each slot (board rear components clear the plate) |
| USB notch | 12 mm wide, open to the top edge, 6 mm below the board's top edge |
| Tripod nut | hex pocket 11.2 mm across flats, 5.8 mm deep, open at the underside; 7 mm through hole |
| Zip-tie holes | 2 x 4 mm, at X = +/-14, Y = 32 |

The USB connector edge of the board goes at the top (under the notch). Chamfers were skipped.

## Print settings

- Material: PETG (preferred) or PLA; Bambu Lab X1C, 0.4 mm nozzle.
- 0.2 mm layer height, 4 walls, 30 % infill, **no supports**.
- Orientation: base plate flat on the bed, vertical plate up (as exported). The hex pocket is
  open to the bed, so nothing needs bridging.

## Assembly

1. After printing, press a 1/4-20 hex nut into the pocket from underneath (a few taps; a
   drop of CA glue is optional).
2. Seat the camera board on the four standoffs, lens through the 20 mm hole, USB connector
   toward the notch.
3. Fasten with four M2 screws and M2 nuts, nuts on the back of the vertical plate. The
   stack is board 1.6 + standoff 3 + plate 4 = ~8.6 mm, plus a 1.6 mm nut, so use **M2 x 10
   (minimum) or M2 x 12**. M2 x 6 or M2 x 8 are too short to reach the nut.
4. Optional: thread a zip tie through the two base holes to secure a USB cable.

## Different hole pitch

The slots accept board hole pitches (square pattern, centre-to-centre) from 26 to 32 mm. If
your board is outside that range, change `HOLE_PITCH_MM` (slot centre pitch) and
`PITCH_MIN` / `PITCH_MAX` (which size the slot length) in `tools/make_bracket.py` and
regenerate. Check the actual board hole pitch with calipers before printing; the
manufacturer's drawing was not confirmed.

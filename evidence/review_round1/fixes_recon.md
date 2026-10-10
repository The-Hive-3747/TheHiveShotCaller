# Finding 9 fix: many-to-one track matching (hiveshot/recon.py)

## Change
- New module-level `merge_fragments(tracks, gap_s=0.25, px=40.0) -> list[Track2D]`: joins same-camera
  tracks where the later one starts 0 <= gap <= gap_s after the earlier one ends and its first point lies
  within `px * (1 + gap/0.1 s)` of a constant-velocity pixel extrapolation (last <=4 points) of the earlier
  one. Each track is predecessor/successor at most once (smallest gaps first). Merged track: new
  track_id (max input id + 1, ...), detections concatenated and sorted by t. Untouched tracks are the
  original objects. `gap_s <= 0` disables merging.
- `StereoReconstructor.__init__` gains kwargs `merge_gap_s=0.25`, `merge_px=40.0` (appended; existing
  signatures unchanged). `match_tracks` merges both cameras' tracks before the Hungarian step, so
  returned pairs may contain merged Track2D objects (`reconstruct_all` Track3D ids come from cam A).

## Tests (tests/test_recon.py, additive; no thresholds changed)
- `test_split_track_still_reconstructs_full_flight`: synth_basic, cam1 shot 2 split at midpoint with 4
  frames removed; asserts 6 Track3D and shot-2 points >= 90% of truth points; also asserts that with
  `merge_gap_s=0` shot 2 falls below 90% (demonstrates the bug).
- `test_merge_fragments_rejects_distant_balls`: tracks 0.1 s apart in time, 300 px apart are not merged;
  control with same position merges (20 sorted detections, fresh id).

## Output
```
$ .venv\Scripts\python.exe -m pytest tests/test_recon.py -q
..............                                                           [100%]
(14 passed)
$ .venv\Scripts\python.exe -m ruff check hiveshot/recon.py tests/test_recon.py
All checks passed!
```

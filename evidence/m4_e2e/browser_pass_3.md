# Browser pass 3 (2026-10-10 18:30, source app on 8765, build.ps1 running concurrently)

Verified in the real browser against the real backend:
- Fresh load: no console errors. Dashboard, Setup tab (5-step wizard: Cameras, Tags, Verify HIVE tags, Colors, Done) render; wizard copy and controls present; "No cameras detected yet" shown (no cameras attached).
- Status warnings surface in the UI model: "camera cam0 dropped 29 frames (processing too slow)" (CPU contention from the concurrent build); shots carry dropped_during_flight; the shot that lost 20 frames is UNKNOWN, not misclassified. Timing exposed: detect_ms ~17 per frame per camera under load (to be re-measured idle).
- Demo mode: "Run demo" -> status.demo true, DEMO badge visible, button becomes "Exit demo", session "Demo 2026-10-10 18:31" created, Dashboard tab active. "Exit demo" -> see appended result.
- Found and routed: /api/setup/status returned no detected cameras and no recommendations while the pipeline ran on file sources (backend worker fixing).
- Exit demo result: POST /api/demo/stop returns 200 immediately; status.demo stayed true for a few seconds while the pipeline stopped, then became false and the user config (synth_basic sources) was restored. Not a defect, but the UI should show "stopping..." until status confirms. Noted for the UI owner.

# Browser pass 2 (2026-10-10 15:35, source app on 8765, data/dev)

- Found and fixed: ui/app.js line 196 had a literal newline inside a string literal (from UI round 3), which broke the whole UI (Uncaught SyntaxError). Added tests/test_ui_static.py::test_js_modules_parse_with_node (Node.js LTS installed via winget) as a syntax gate.
- After fix: dashboard, ENDED camera state, session picker, shots table with "burst 1 · #n" and result filter all render; no console errors on a fresh load.
- Session 9400eff0 (run while build.ps1 and four refuter agents were loading the CPU): 47 dropped frames per camera; shots 11 and 12 truncated at t=1.65 s mid-air (last z 83 and 75 in) and classified MISS. Truth: shot at 1.0 s is MADE. Two issues:
  1. Mid-air-lost tracks must be classified UNKNOWN, not MISS (classification bug, independent of load).
  2. Real-time headroom must be measured on an idle machine and the UI must warn when dropped > 0.
- Session 8d03e4db (earlier, idle CPU): 0 dropped, 4 made, matches truth.

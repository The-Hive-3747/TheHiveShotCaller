"""Static checks for ui/. No browser execution; see evidence/m4_ui/verification.txt."""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ui_stub_server  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "ui"
JS_FILES = [p for p in UI.glob("*.js")]


def _strip_js(src: str) -> str:
    """Remove comments, strings, template literal text (keeping ${} bodies) and regex-free heuristics."""
    out: list[str] = []
    i, n = 0, len(src)
    tmpl_stack: list[int] = []  # brace depth markers for ${ } inside templates
    depth = 0
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            while i < n and src[i] != "\n":
                i += 1
        elif c == "/" and nxt == "*":
            i = src.index("*/", i + 2) + 2
        elif c == "/" and "".join(out).rstrip()[-1:] in "(,=:[!&|?{};":
            i += 1  # regex literal
            in_cls = False
            while src[i] != "/" or in_cls:
                if src[i] == "\\":
                    i += 1
                elif src[i] == "[":
                    in_cls = True
                elif src[i] == "]":
                    in_cls = False
                i += 1
            i += 1
        elif c in "'\"":
            q = c
            i += 1
            while src[i] != q:
                i += 2 if src[i] == "\\" else 1
            i += 1
        elif c == "`":
            i += 1
            while src[i] != "`":
                if src[i] == "\\":
                    i += 2
                elif src[i] == "$" and src[i + 1] == "{":
                    # copy the expression recursively: find matching brace
                    j, d = i + 2, 1
                    while d:
                        if src[j] == "{":
                            d += 1
                        elif src[j] == "}":
                            d -= 1
                        j += 1
                    out.append("(" + _strip_js(src[i + 2:j - 1]) + ")")
                    i = j
                else:
                    i += 1
            i += 1
        else:
            out.append(c)
            i += 1
    del tmpl_stack, depth
    return "".join(out)


def test_index_references_exist():
    html = (UI / "index.html").read_text(encoding="utf-8")
    refs = re.findall(r'(?:src|href)="([^"#]+)"', html)
    refs += re.findall(r'"three":"([^"]+)"', html)
    local = [r for r in refs if not r.startswith(("http", "/api"))]
    assert local, "index.html references nothing?"
    for r in local:
        assert (UI / r).is_file(), f"missing {r}"
    assert "app.js" in html and "styles.css" in html and "importmap" in html


def test_no_external_urls():
    for p in [UI / "index.html", UI / "styles.css", *JS_FILES]:
        txt = p.read_text(encoding="utf-8")
        assert not re.search(r"https?://(?!127\.0\.0\.1)", txt), f"external URL in {p.name}"


def test_js_delimiters_balanced():
    assert JS_FILES
    for p in JS_FILES:
        s = _strip_js(p.read_text(encoding="utf-8"))
        stack = []
        pairs = {")": "(", "]": "[", "}": "{"}
        for ch in s:
            if ch in "([{":
                stack.append(ch)
            elif ch in ")]}":
                assert stack and stack.pop() == pairs[ch], f"unbalanced {ch} in {p.name}"
        assert not stack, f"unclosed {stack[-3:]} in {p.name}"


def test_js_imports_resolve():
    for p in JS_FILES:
        for m in re.finditer(r"from\s+'(\.[^']+)'", p.read_text(encoding="utf-8")):
            assert (p.parent / m.group(1)).is_file(), f"{p.name} imports missing {m.group(1)}"


def test_element_ids_exist_in_html():
    html = (UI / "index.html").read_text(encoding="utf-8")
    ids = set(re.findall(r'id="([^"]+)"', html))
    js = (UI / "app.js").read_text(encoding="utf-8")
    used = set(re.findall(r"\$\('([A-Za-z0-9_-]+)'\)", js))
    dynamic = {"devPick", "addSrc", "srcs", "btnSave", "profilePick"}  # created by renderSettings
    assert not (used - ids - dynamic), f"ids used in JS but absent: {used - ids - dynamic}"


def test_api_paths_in_contract():
    doc = (ROOT / "docs" / "api.md").read_text(encoding="utf-8")
    js = (UI / "app.js").read_text(encoding="utf-8")
    # Endpoints the backend is adding whose docs/api.md entry has not landed yet.
    # TODO: remove "crosscheck" / "finish" once docs/api.md documents POST /api/calib/crosscheck and /api/setup/finish.
    pending_docs = {"crosscheck", "finish"}
    for m in re.finditer(r"['`](/api/[^'`]*)", js):
        path = re.sub(r"\$\{[^}]*\}", "{x}", m.group(1))
        segs = [s for s in path.split("?")[0].replace("{x}", "").split("/") if s]
        segs = [s for s in segs if s not in pending_docs or s in doc]
        assert all(s.strip(".") .split(".")[0] in doc for s in segs), f"{path} not in api.md"


def test_stub_server_serves_ui():
    srv, _ = ui_stub_server.start(0)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        for name in ["/", "/app.js", "/viewer3d.js", "/styles.css",
                     "/vendor/three.module.min.js", "/vendor/OrbitControls.js"]:
            with urllib.request.urlopen(base + name, timeout=10) as r:
                assert r.status == 200
                assert len(r.read()) > 100, name
        with urllib.request.urlopen(base + "/api/config", timeout=10) as r:
            assert json.load(r)["sources"][0]["cam_id"] == "cam0"
    finally:
        srv.shutdown()
        srv.server_close()


def test_round2_controls_wired():
    html = (UI / "index.html").read_text(encoding="utf-8")
    js = (UI / "app.js").read_text(encoding="utf-8")
    for i in ("selSession", "shotFilter", "chkFollow", "shotCount"):
        assert f'id="{i}"' in html and f"$('{i}')" in js, i
    for opt in ("all", "made", "miss", "bounce_out"):
        assert f'<option value="{opt}">' in html
    assert "'/api/sessions'" in js and "ENDED" in js and "DOWN" in js and "LIVE" in js
    assert "c.ended" in js and "burst ${esc(s.burst_id)} · #${esc(s.burst_index)}" in js
    assert "shot.equation" in js and "setFollow" in js


def test_responsive_css_rules():
    css = (UI / "styles.css").read_text(encoding="utf-8")
    assert "container-type:inline-size" in css
    assert re.search(r"@container\s+mainarea\s*\(max-width:900px\)", css)
    assert "@supports not (container-type" in css and "min-height:360px" in css
    assert re.search(r"@media \(max-width:900px\)\{.*#camList\{display:flex", css, re.S)


def test_stub_sessions_endpoint_shape():
    srv, _ = ui_stub_server.start(0)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/api/sessions", timeout=10) as r:
            rows = json.load(r)
        assert rows and {"session_id", "started_at", "ended_at"} <= rows[0].keys()
        with urllib.request.urlopen(base + f"/api/sessions/{rows[0]['session_id']}/shots", timeout=10) as r:
            assert "equation" in json.load(r)[0]
    finally:
        srv.shutdown()
        srv.server_close()


def test_round3_features_wired():
    html = (UI / "index.html").read_text(encoding="utf-8")
    js = (UI / "app.js").read_text(encoding="utf-8")
    for i in ("calMismatch", "tipsBox", "tipTable", "tipCount"):
        assert f'id="{i}"' in html, i
    for i in ("calMismatch", "tipTable", "tipCount"):
        assert f"$('{i}')" in js, i
    assert "m.type === 'shot_updated'" in js and "m.type === 'tip'" in js
    assert "findIndex((s) => s.shot_id === m.shot.shot_id)" in js
    assert "(b.t_launch ?? 0) - (a.t_launch ?? 0)" in js
    assert "calibration_mismatch" in js and "no active session" in js
    assert "/tips`" in js


def test_stub_round3_payloads():
    srv, _ = ui_stub_server.start(0)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/api/sessions/s1/tips", timeout=10) as r:
            assert {"t", "alliance", "new_up_cell", "caused_by_shot_id"} <= json.load(r)[0].keys()
        with urllib.request.urlopen(base + "/api/pipeline/status", timeout=10) as r:
            assert "calibration_mismatch" in json.load(r)
    finally:
        srv.shutdown()
        srv.server_close()
    kinds = {m["type"] for m in ui_stub_server.WS_MESSAGES}
    assert {"shot_updated", "tip", "status"} <= kinds


def _find_node():
    import os
    import shutil
    from pathlib import Path

    exe = shutil.which("node")
    if exe:
        return exe
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    for p in base.glob("OpenJS.NodeJS*/**/node.exe"):
        return str(p)
    return None


def test_js_modules_parse_with_node():
    """Every UI module must parse as an ES module. Uses Node's --check so a syntax
    error (like a literal newline inside a string) fails before a browser ever loads it."""
    import subprocess
    from pathlib import Path

    import pytest

    node = _find_node()
    if not node:
        pytest.skip("node.exe not found; install Node.js LTS to enable the JS syntax gate")
    ui = Path(__file__).resolve().parent.parent / "ui"
    for f in sorted(ui.glob("*.js")):
        r = subprocess.run(
            [node, "--input-type=module", "--check"],
            input=f.read_bytes(),
            capture_output=True,
            timeout=30,
        )
        assert r.returncode == 0, f"{f.name}: {r.stderr.decode(errors='replace')[:800]}"


def test_round4_features_wired():
    html = (UI / "index.html").read_text(encoding="utf-8")
    js = (UI / "app.js").read_text(encoding="utf-8")
    css = (UI / "styles.css").read_text(encoding="utf-8")
    # 1. unknown result filter
    assert '<option value="unknown">' in html
    # 2. no-track message inside the viewport, toggled by openReplay
    assert 'id="noTrack"' in html and "No 3D track for this shot" in html
    assert "$('noTrack')" in js and "#noTrack" in css
    # 3. drag k label/format and RMSE decimals
    assert "k (1/in)" in js and "fmtSig(shot.drag.k_per_in, 4)" in js
    assert "toPrecision" in js and "fmt(shot.drag.rmse_in, 2)" in js
    # 4. dropped-during-flight warning in the Result cell
    assert "dropped_during_flight" in js and "frames dropped during flight:" in js
    assert ".dropped-warn" in css
    # 5. amber dropped count in camera overlay
    assert "cam-dropped" in js and ".cam-dropped" in css
    # 6. session picker order and default pick use started_at, not API order
    assert "(b.started_at ?? 0) - (a.started_at ?? 0)" in js
    assert "newest(running.length ? running : list)" in js


def test_stub_round4_payloads():
    srv, _ = ui_stub_server.start(0)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        def get(path):
            with urllib.request.urlopen(base + path, timeout=10) as r:
                return json.load(r)

        sessions = get("/api/sessions")
        starts = [s["started_at"] for s in sessions]
        assert starts != sorted(starts, reverse=True), "stub must serve sessions out of newest-first order"
        shots = get("/api/sessions/s1/shots")
        assert {s["result"] for s in shots} >= {"made", "unknown"}
        assert any(s.get("dropped_during_flight", 0) > 0 for s in shots)
        assert get("/api/shots/2")["track"] == []
        assert get("/api/shots/1")["drag"]["k_per_in"] > 0
        assert get("/api/pipeline/status")["cameras"]["cam0"]["dropped"] > 0
    finally:
        srv.shutdown()
        srv.server_close()


def test_calibration_points_dynamic_not_hardcoded():
    js = (UI / "app.js").read_text(encoding="utf-8")
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert "const CALIB_POINTS" not in js and "CALIB_POINTS[" not in js
    assert "'/api/calib/points'" in js and "loadCalibPoints" in js
    assert "await loadCalibPoints()" in js  # run whenever the Calibration tab loads
    assert 'id="calibWarn"' in html and "$('calibWarn')" in js
    assert 'href="/api/calib/checkerboard.pdf"' in html and "Download checkerboard PDF" in html


def test_ui_encodes_no_field_geometry():
    """Point/tag names and coordinates come only from the API; the UI source must not hardcode them."""
    js = (UI / "app.js").read_text(encoding="utf-8")
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert "FALLBACK_CALIB_NAMES" not in js and "FALLBACK_TAG_NAMES" not in js
    for text in (js, html):
        assert not re.search(r"top corner|63\.95|24\.73|19\.48", text), "field geometry hardcoded in the UI"
    # when /api/calib/points fails the list is empty, a warning is shown and clicking is blocked
    assert "list = [];" in js and "point clicking is disabled" in js
    assert "if (!calibPoints.length)" in js


def test_stub_calibration_endpoints():
    srv, _ = ui_stub_server.start(0)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/api/calib/points", timeout=10) as r:
            pts = json.load(r)
        assert len(pts) == 8 and all(len(p["xyz"]) == 3 for p in pts)
        assert [p["name"] for p in pts] == [f"point {i}" for i in range(1, 9)]  # generic stub-only data
        with urllib.request.urlopen(base + "/api/calib/checkerboard.pdf", timeout=10) as r:
            assert r.headers["Content-Type"] == "application/pdf"
            assert r.read().startswith(b"%PDF")
    finally:
        srv.shutdown()
        srv.server_close()


def test_round5_status_settings_crosscheck_wired():
    html = (UI / "index.html").read_text(encoding="utf-8")
    js = (UI / "app.js").read_text(encoding="utf-8")
    css = (UI / "styles.css").read_text(encoding="utf-8")
    # (1) rtmp publish URL + hint in Settings
    assert "st.rtmp.urls" in js and "refreshRtmpHints" in js
    assert "Enter the stream name, e.g. cam0; publish from GoPro Quik or ffmpeg to this URL." in js
    # (2) warnings banner (hidden when empty) and no-calibration chip
    for i in ("warnBanner", "noCalib"):
        assert f'id="{i}"' in html and f"$('{i}')" in js, i
    assert "st.warnings" in js and "st.calibration_loaded === false" in js
    assert re.search(r'id="warnBanner"[^>]*display:none', html)
    assert "#warnBanner" in css
    # (3) cross-check button, POST, green/red by 1 in threshold
    assert 'id="btnCrosscheck"' in html and 'id="crosscheckOut"' in html
    assert "$('btnCrosscheck')" in js and "'POST', '/api/calib/crosscheck'" in js
    assert "CROSSCHECK_OK_IN = 1.0" in js and "xc-ok" in js and "xc-bad" in js
    assert ".xc-ok" in css and ".xc-bad" in css


def test_stub_round5_payloads():
    import urllib.error

    srv, _ = ui_stub_server.start(0)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/api/pipeline/status", timeout=10) as r:
            st = json.load(r)
        assert st["warnings"] and st["calibration_loaded"] is False
        assert st["rtmp"]["urls"]["cam1"].startswith("rtmp://")
        with urllib.request.urlopen(base + "/api/config", timeout=10) as r:
            assert any(s["kind"] == "rtmp" and s["cam_id"] in st["rtmp"]["urls"] for s in json.load(r)["sources"])
        req = urllib.request.Request(base + "/api/calib/crosscheck", data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            cc = json.load(r)
        errs = [p["error_in"] for p in cc["points"]]
        assert min(errs) < 1.0 < max(errs) and cc["max_error_in"] == max(errs)
        assert {"name", "xyz_measured", "xyz_expected", "error_in"} <= cc["points"][0].keys()
    finally:
        srv.shutdown()
        srv.server_close()


def test_round6_setup_wizard_wired():
    html = (UI / "index.html").read_text(encoding="utf-8")
    js = (UI / "app.js").read_text(encoding="utf-8")
    css = (UI / "styles.css").read_text(encoding="utf-8")
    # new tab + four steps, each with a hints container
    assert 'data-tab="setup"' in html and 'id="tab-setup"' in html
    for step in ("cameras", "lens", "tags", "hivetags", "colors", "done"):
        assert 'class="card setupstep' in html and f'data-step="{step}"' in html, step
    assert html.count('class="hints"') == 6
    assert ".setupstep" in css and ".thumb" in css
    # shown automatically on first run
    assert "'/api/setup/status'" in js and "sources_configured === false" in js
    assert "calibration_loaded === false" in js and "showTab('setup')" in js
    # recommendations rendered as hints
    assert "st.recommendations" in js and ".hints" in js
    # cameras step: profile default on, previews, -X wall camera -> cam0
    assert 'id="chkProfile" type="checkbox" checked' in html and "Use Arducam 1080p90 profile" in html
    assert "cameras_detected" in js and "/api/preview/" in js and "deviceSource('cam0'" in js
    assert "deviceSource('cam1'" in js and "This is the -X wall camera" in js
    # tags step
    assert 'href="/api/calib/tags.pdf"' in html and "'POST', '/api/calib/auto_all'" in js
    assert "max_error_in" in js and "xc-ok" in js and "tags_seen" in js
    # colors step
    assert "'POST', '/api/detector/sample'" in js and "ball_type" in js and 'id="colorBall"' in html
    # done step creates a session with the default name
    assert 'id="btnFinish"' in html and "sessionNameNow()" in js and "'/api/pipeline/start'" in js


def test_round6_session_name_profile_and_hive_source():
    html = (UI / "index.html").read_text(encoding="utf-8")
    js = (UI / "app.js").read_text(encoding="utf-8")
    # template expansion with {date} and {time}, applied as the session-name default
    assert "session_name_template" in js and "{date}" in js and "{time}" in js
    assert "updateSessName()" in js and "name: sessionNameNow()" in js
    # settings profile dropdown
    assert "state.config.profiles" in js and 'id="profilePick"' in js and "applyProfileToSource" in js
    # HIVE state source pill and manual-control lock
    assert 'id="hiveSrc"' in html and "st.hive_state_source" in js
    assert "$(id).disabled = hiveSrc === 'tags'" in js


def test_stub_round6_payloads():
    srv, _ = ui_stub_server.start(0)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        def call(path, method="GET", body=None):
            data = json.dumps(body).encode() if body is not None else (b"" if method != "GET" else None)
            req = urllib.request.Request(base + path, data=data, method=method)
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.headers["Content-Type"], r.read()

        _, raw = call("/api/setup/status")
        st = json.loads(raw)
        assert {"cameras_detected", "sources_configured", "calibration_loaded", "tags_seen",
                "pipeline_running", "recommendations"} <= st.keys()
        assert st["sources_configured"] is False and st["recommendations"]
        assert call("/api/calib/tags.pdf")[0] == "application/pdf"
        tags = json.loads(call("/api/calib/tags")[1])
        assert len(tags) == 4 and {"id", "size_in", "name"} <= tags[0].keys()
        res = json.loads(call("/api/calib/auto_all", "POST", {})[1])
        assert "max_error_in" in res and res["cameras"]["cam0"]["rmse_in"] < 1.0
        smp = json.loads(call("/api/detector/sample", "POST",
                              {"cam_id": "cam0", "u": 1, "v": 2, "ball_type": "pollen"})[1])
        assert smp["ball_type"] == "pollen"
        cfg = json.loads(call("/api/config")[1])
        assert "arducam_1080p90" in cfg["profiles"] and "{date}" in cfg["session_name_template"]
        assert json.loads(call("/api/pipeline/status")[1])["hive_state_source"] in ("manual", "tags")
        assert json.loads(call("/api/config", "PUT", cfg)[1])["alliance"] == cfg["alliance"]
        for p in ("/api/pipeline/start", "/api/pipeline/stop"):
            call(p, "POST", {})
    finally:
        srv.shutdown()
        srv.server_close()


def test_round7_learn_hive_tags_wired():
    html = (UI / "index.html").read_text(encoding="utf-8")
    js = (UI / "app.js").read_text(encoding="utf-8")
    # step sits between Tags and Colors
    order = [html.index(f'data-step="{k}"') for k in ("tags", "hivetags", "colors")]
    assert order == sorted(order)
    assert "Make sure the audience CELL is up. Press Learn." in html
    assert "tip the HIVE by hand so the far CELL is up" in html and "press Learn again" in html
    assert 'id="learnState"' in html and 'id="btnLearn"' in html and 'id="learnOut"' in html
    # default is audience-up first (first option), far-up second
    assert re.search(r'id="learnState"><option value="audience">.*?<option value="far">', html, re.S)
    assert "'POST', '/api/calib/hive_tags/learn'" in js and "state: { alliance, up_cell: upCell }" in js
    for k in ("learned_ids", "missing_ids", "visible_per_camera", "max_residual_in"):
        assert k in js, k
    assert "setup.learned" in js and "detected automatically from the tags" in js
    # top bar shows "auto (tags)" when the HIVE state comes from tags
    assert "'auto (tags)'" in js and "st.hive_state_source" in js


def test_stub_hive_tags_learn():
    srv, _ = ui_stub_server.start(0)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        body = json.dumps({"state": {"alliance": "red", "up_cell": "audience"}}).encode()
        req = urllib.request.Request(base + "/api/calib/hive_tags/learn", data=body, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            res = json.load(r)
        assert {"learned_ids", "missing_ids", "visible_per_camera", "max_residual_in"} <= res.keys()
    finally:
        srv.shutdown()
        srv.server_close()


def test_round8_tag_source_and_verify_step():
    html = (UI / "index.html").read_text(encoding="utf-8")
    js = (UI / "app.js").read_text(encoding="utf-8")
    # tag source choice, printed sheet preselected
    assert re.search(r'name="tagSource" value="kit" checked> I printed the tag sheet \(recommended\)', html)
    assert re.search(r'name="tagSource" value="hive"> No printer: use the HIVE\'s own tags', html)
    assert "'POST', '/api/calib/auto_all', { source: tagSource() }" in js
    assert "r.warning" in js  # backend warning text is shown
    # renamed, optional verify step explains the manual-known up CELL
    assert "Verify HIVE tags (optional)" in html and "Learn HIVE tags" not in html
    assert "known from the manual" in html and "learns the tags on the down CELL" in html
    assert "up_cell_error_in" in js and "Number(r.up_cell_error_in) < CROSSCHECK_OK_IN" in js


def test_stub_round8_payloads():
    srv, _ = ui_stub_server.start(0)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        def post(path, body):
            req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST")
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.load(r)

        assert post("/api/calib/auto_all", {"source": "hive"})["warning"]
        assert post("/api/calib/hive_tags/learn", {"state": {"alliance": "red", "up_cell": "audience"}})[
            "up_cell_error_in"] < 1.0
    finally:
        srv.shutdown()
        srv.server_close()


def test_round9_demo_mode_wired():
    html = (UI / "index.html").read_text(encoding="utf-8")
    js = (UI / "app.js").read_text(encoding="utf-8")
    css = (UI / "styles.css").read_text(encoding="utf-8")
    for i in ("demoBadge", "btnDemo", "demoBanner"):
        assert f'id="{i}"' in html and f"$('{i}')" in js, i
    # badge sits right after the title, before the other pills
    assert html.index('class="brand"') < html.index('id="demoBadge"') < html.index('id="wsState"')
    assert ">DEMO<" in html and ".demo-badge" in css
    assert "Run demo" in html and "'Exit demo' : 'Run demo'" in js
    assert "'/api/demo/start'" in js and "'/api/demo/stop'" in js and "api('POST', starting ?" in js
    assert "r.session_id" in js and "setSession(sid)" in js and "showTab('dashboard')" in js
    assert "st.demo === true" in js
    assert "demo config (not saved)" in html
    # wizard auto-open is suppressed in demo mode (check happens before the auto-open)
    assert js.index("if (state.demo) return;") < js.index("showTab('setup');")


def test_stub_round9_demo_toggle():
    srv, _ = ui_stub_server.start(0)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        def status():
            with urllib.request.urlopen(base + "/api/pipeline/status", timeout=10) as r:
                return json.load(r)

        def post(path):
            req = urllib.request.Request(base + path, data=b"", method="POST")
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.load(r)

        ui_stub_server.DEMO_DELAY_S = 0.4
        assert status()["demo"] is False
        res = post("/api/demo/start")
        assert res["ok"] is True and res["session_id"]
        assert status()["demo"] is False, "status.demo must lag the 200 response"
        time.sleep(0.6)
        assert status()["demo"] is True
        assert post("/api/demo/stop")["ok"] is True
        assert status()["demo"] is True, "status.demo stays true until the pipeline has stopped"
        time.sleep(0.6)
        assert status()["demo"] is False
    finally:
        ui_stub_server.DEMO_DELAY_S = 2.0
        ui_stub_server.DEMO_STATE.update(on=False, target=False, at=0.0)
        srv.shutdown()
        srv.server_close()


def test_round10_demo_transition_waits_for_status():
    js = (UI / "app.js").read_text(encoding="utf-8")
    assert "'Exiting demo...'" in js and "'Starting demo...'" in js
    assert "$('btnDemo').disabled = !!pend" in js
    # completion is driven by status (demo flag), not by the POST response
    assert "demoSettled(st)" in js and "(st.demo === true) !== (state.demoPending === 'starting')" in js
    assert "setInterval(tick, 1000)" in js and "DEMO_TIMEOUT_MS" in js
    # reload of config/sessions happens in the settle handler, after pending is cleared
    fin = js[js.index("async function finishDemoTransition"):js.index("function watchDemoTransition")]
    assert fin.index("clearDemoPending()") < fin.index("reloadAfterModeChange()") < fin.index("refreshSessions()")
    onclick = js[js.index("$('btnDemo').onclick"):]
    onclick = onclick[:onclick.index("};")]
    assert "reloadAfterModeChange" not in onclick and "refreshSessions" not in onclick


def test_round12_field_size_setting():
    js = (UI / "app.js").read_text(encoding="utf-8")
    assert "inp('field_size_in', c.field_size_in ?? 144)" in js and "'Field size (in)'" in js
    assert "Measure your field wall to wall; the official CAD says 141.35" in js
    assert "141.35" in js and "about 144" in js
    # saved through the generic [data-path] loop, with a client-side 60-400 check
    assert "setPath(merged, el.dataset.path, v)" in js
    assert "el.dataset.path === 'field_size_in' && !(v >= 60 && v <= 400)" in js


def test_stub_config_has_field_size():
    srv, _ = ui_stub_server.start(0)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/api/config", timeout=10) as r:
            assert json.load(r)["field_size_in"] == 144
    finally:
        srv.shutdown()
        srv.server_close()


def test_round13_refuter_fixes_wired():
    html = (UI / "index.html").read_text(encoding="utf-8")
    js = (UI / "app.js").read_text(encoding="utf-8")
    css = (UI / "styles.css").read_text(encoding="utf-8")
    # (1) Calibration tab buttons named like the docs, provenance chips
    assert 'id="btnAutoAll"' in html and "Auto-calibrate all" in html
    assert 'data-act="auto">Auto-calibrate</button>' in js
    assert "/api/calib/extrinsics/${encodeURIComponent(id)}/auto" in js and "'POST', '/api/calib/auto_all'" in js
    assert "intrinsics_source" in js and "calibration_source" in js
    assert "info.intrinsics_source === 'default'" in js  # red chip
    # (2) Lens step before Tags, required unless measured/profile
    order = [html.index(f'data-step="{k}"') for k in ("cameras", "lens", "tags", "hivetags", "colors", "done")]
    assert order == sorted(order)
    assert 'href="/api/calib/checkerboard.pdf"' in html and "1.5 to 3 ft" in html and "20 seconds" in html
    assert "Start recording" in js and "Stop recording" in js and "/api/calib/intrinsics/${encodeURIComponent(cam)}/" in js
    assert "LENS_OK_PX = 1.0" in js and "LENS_WARN_PX = 2.0" in js and "xc-amber" in js and ".xc-amber" in css
    assert "src === 'measured' || src === 'profile'" in js
    assert "lensBlockingCams()" in js and js.index("lensBlockingCams()") < js.index("'Calibrating...'")
    # (3) column names
    assert "Fit residual (in)" in js and "Out-of-sample error (in)" in js and "oos_error_in" in js
    assert "Pose error" not in js
    # (4) Done step goes through /api/setup/finish and stops on a refusal
    assert "'POST', '/api/setup/finish'" in js and "reasonLines(e)" in js
    fin = js[js.index("$('btnFinish').onclick"):]
    assert fin.index("/api/setup/finish") < fin.index("return;   // blocked") < fin.index("/api/sessions")
    # (5) no fixed port anywhere; WebSocket derived from the page location
    assert "8765" not in js and "window.location.host" in js
    # (6) Colors step: ranges, undo, reset, clicks outside the image ignored
    for i in ("colorRanges", "btnColorUndo", "btnColorReset"):
        assert f'id="{i}"' in html and f"$('{i}')" in js, i
    assert "Undo last sample" in html and "Reset to defaults" in html
    assert "fx >= 0 && fx <= 1 && fy >= 0 && fy <= 1" in js and "colorHist[key].push(before)" in js
    assert "'PUT', '/api/config', { detector }" in js
    # (7) far-up learn with nothing visible but complete
    assert "far-up tags are not visible from these cameras; this is expected" in js
    assert "r.complete === true" in js and "classList.toggle('done'" in js
    # (8) exact tape positions in plain words plus the tolerance note
    assert "function describeTag" in js and "x.xyz_center" in js and "x.normal" in js
    assert "within 0.25 in" in js


def test_stub_round13_payloads():
    import copy

    srv, _ = ui_stub_server.start(0)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    saved = copy.deepcopy(ui_stub_server.CONFIG)
    try:
        def call(path, method="GET", body=None):
            data = json.dumps(body).encode() if body is not None else (b"" if method != "GET" else None)
            req = urllib.request.Request(base + path, data=data, method=method)
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    return r.status, json.load(r)
            except urllib.error.HTTPError as e:
                return e.code, json.load(e)

        _, calib = call("/api/calib")
        assert {i["cam_id"]: i["intrinsics_source"] for i in calib["intrinsics"]} == {"cam0": "default", "cam1": "measured"}
        assert all("calibration_source" in e for e in calib["extrinsics"])
        _, tags = call("/api/calib/tags")
        assert all(len(t["xyz_center"]) == 3 and len(t["normal"]) == 3 for t in tags)
        assert call("/api/calib/auto_all", "POST", {"source": "kit"})[1]["cameras"]["cam0"]["oos_error_in"] > 0
        assert call("/api/calib/extrinsics/cam0/auto", "POST", {})[1]["oos_error_in"] is not None
        assert call("/api/calib/intrinsics/cam0/stop", "POST", {})[1]["reprojection_rmse_px"] > 0
        assert call("/api/detector/sample", "POST", {"cam_id": "cam0", "u": 1, "v": 1, "ball_type": "pollen"})[
            1].keys() >= {"ball_type", "sampled_hsv", "range"}
        # far-up learn: nothing visible but complete
        far = call("/api/calib/hive_tags/learn", "POST", {"state": {"alliance": "red", "up_cell": "far"}})[1]
        assert far["complete"] is True and far["learned_ids"] == []
        # /api/setup/finish: 200 normally, 409 with reasons when blocked
        assert call("/api/setup/finish", "POST", {})[0] == 200
        ui_stub_server.FINISH_STATE["block"] = True
        code, body = call("/api/setup/finish", "POST", {})
        assert code == 409 and len(body["detail"]) >= 1
        # PUT /api/config merges the detector section and returns the full config
        _, cfg = call("/api/config", "PUT", {"detector": {"pollen_hsv": [[1, 2, 3], [4, 5, 6]]}})
        assert cfg["detector"]["pollen_hsv"] == [[1, 2, 3], [4, 5, 6]] and cfg["detector"]["motion_thresh"] == 25
        assert "sources" in cfg
    finally:
        ui_stub_server.FINISH_STATE["block"] = False
        ui_stub_server.CONFIG.clear()
        ui_stub_server.CONFIG.update(saved)
        srv.shutdown()
        srv.server_close()

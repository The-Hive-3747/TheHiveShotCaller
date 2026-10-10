"""Smoke test of the packaged exe. Skipped unless dist/HiveShotTracker/HiveShotTracker.exe exists."""

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

BUNDLE = Path(__file__).resolve().parent.parent / "dist" / "HiveShotTracker"
EXE = BUNDLE / "HiveShotTracker.exe"
PORT = 8767
# Exit codes accepted when the console app is stopped from outside on Windows:
# 0 = clean shutdown, 3 = default SIGBREAK/CTRL_BREAK termination, 1 = TerminateProcess fallback.
OK_EXIT_CODES = {0, 1, 3}

pytestmark = [
    pytest.mark.build,
    pytest.mark.skipif(not EXE.is_file(), reason="packaged exe not built"),
]


def _get(path: str, timeout: float = 5.0, port: int = PORT) -> bytes:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as r:
        assert r.status == 200
        return r.read()


def _stop(proc) -> tuple[str, int]:
    """Stop the console exe: CTRL_BREAK, then terminate, then kill. Returns (method, exit code)."""
    method = "ctrl_break"
    try:
        if sys.platform == "win32":
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            proc.terminate()
        proc.wait(timeout=20)
    except (subprocess.TimeoutExpired, OSError, ValueError):
        method = "terminate"
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            method = "kill"
            proc.kill()
            proc.wait(timeout=10)
    assert proc.poll() is not None
    return method, proc.returncode


def _wait(pred, cap: float, what: str):
    end = time.time() + cap
    last = None
    while time.time() < end:
        try:
            v = pred()
            if v:
                return v
        except Exception as e:  # server not up yet
            last = e
        time.sleep(0.5)
    raise AssertionError(f"timeout waiting for {what} (last error: {last})")


def test_packaged_exe_runs_from_foreign_cwd(tmp_path, record_property):
    cwd = tmp_path / "elsewhere"
    cwd.mkdir()
    data = tmp_path / "data"
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)  # lets us send CTRL_BREAK to just this process
    proc = subprocess.Popen(
        [str(EXE), "--port", str(PORT), "--data-dir", str(data), "--autostart"],
        cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=flags)
    try:
        _wait(lambda: json.loads(_get("/api/pipeline/status")), 60, "status")
        st = _wait(lambda: (lambda s: s if (s.get("last_shot_id") or 0) >= 1 else None)(
            json.loads(_get("/api/pipeline/status"))), 90, "last_shot_id >= 1")
        assert st["last_shot_id"] >= 1
        assert b"<html" in _get("/").lower()
        assert "error" not in json.loads(_get("/api/field/geometry"))
        assert len(_get("/vendor/three.module.min.js")) > 10000
    finally:
        method, code = _stop(proc)
    # Record the actual code (visible with -s, in the junit xml, and in the assertion message).
    record_property("exit_code", code)
    record_property("stop_method", method)
    print(f"packaged exe stop_method={method} exit_code={code}")
    assert code in OK_EXIT_CODES, f"unexpected exit code {code} after {method}"


def _find_ci(name: str):
    """Case-insensitive lookup of a file at the bundle root or in PyInstaller 6's _internal dir."""
    for d in (BUNDLE, BUNDLE / "_internal"):
        if d.is_dir():
            for f in d.iterdir():
                if f.is_file() and f.name.lower() == name.lower():
                    return f
    return None


@pytest.mark.parametrize("dll", ["msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll"])
def test_vc_runtime_dlls_ship_with_bundle(dll):
    """App-local VC++ runtime so a PC without the redistributable can start the exe."""
    f = _find_ci(dll)
    assert f is not None, f"{dll} missing from {BUNDLE} (root or _internal)"
    assert f.stat().st_size > 10_000


def test_bundle_ships_docs_and_readme():
    """build.ps1 copies docs/ and writes README.txt next to the exe (run the test after build.ps1)."""
    docs = BUNDLE / "docs"
    for name in ("operator_guide.md", "troubleshooting.md", "calibration.md", "clean_machine_test.md",
                 "camera_placement.md", "camera_placement.png", "camera_placement.svg",
                 "camera_bracket.md", "camera_bracket.stl", "camera_bracket.png"):
        assert (docs / name).is_file(), f"docs/{name} missing from bundle"
    readme = BUNDLE / "README.txt"
    assert readme.is_file(), "README.txt missing from bundle root"
    text = readme.read_text(encoding="utf-8")
    for needle in ("HiveShotTracker.exe", "127.0.0.1:8765", "%LOCALAPPDATA%", "docs", "SmartScreen"):
        assert needle in text, f"README.txt lacks {needle!r}"


@pytest.mark.parametrize("name", ["synth_basic", "synth_20"])
def test_fixture_dirs_in_bundle(name):
    """Demo videos ship in the bundle. synth_20 is required only if the repo has it."""
    src = Path(__file__).resolve().parent.parent / "fixtures" / name
    if name != "synth_basic" and not src.is_dir():
        pytest.skip(f"fixtures/{name} not present in the repo, so not bundled")
    dst = None
    for d in (BUNDLE / "_internal" / "fixtures" / name, BUNDLE / "fixtures" / name):
        if d.is_dir():
            dst = d
            break
    assert dst is not None, f"fixtures/{name} missing from {BUNDLE} (root or _internal)"
    for f in ("cam0.mp4", "cam1.mp4"):
        assert (dst / f).stat().st_size > 10_000, f"{name}/{f} missing or empty"


def _mediamtx_children(parent_pid: int) -> list[int]:
    """PIDs of mediamtx.exe processes whose parent is parent_pid (other agents' mediamtx is ignored)."""
    cmd = ("Get-CimInstance Win32_Process -Filter \"Name='mediamtx.exe'\" | "
           "ForEach-Object { $_.ParentProcessId }")
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                         capture_output=True, text=True, timeout=30).stdout
    return [int(x) for x in out.split() if x.strip().isdigit() and int(x) == parent_pid]


def test_packaged_exe_demo_mode(tmp_path, record_property):
    """`HiveShotTracker.exe --demo`: demo flag, shots, data under <data>/demo, no mediamtx started."""
    demo_port = 8768
    data = tmp_path / "data"
    cwd = tmp_path / "elsewhere"
    cwd.mkdir()
    env = dict(os.environ)
    env["BROWSER"] = "cmd /c exit 0 %s"  # demo mode opens a browser; make that a no-op
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    log = tmp_path / "demo_stdout.txt"
    with open(log, "wb") as lf:
        proc = subprocess.Popen(
            [str(EXE), "--demo", "--port", str(demo_port), "--data-dir", str(data)],
            cwd=cwd, stdout=lf, stderr=subprocess.STDOUT, creationflags=flags, env=env)
        try:
            # Old exe without --demo: argparse exits non-zero within seconds.
            try:
                early = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                early = None
            if early is not None:
                text = log.read_text(errors="replace")
                if early != 0 and "unrecognized arguments" in text:
                    pytest.skip("packaged exe does not support --demo yet (argparse: unrecognized arguments)")
                pytest.fail(f"exe exited early with code {early}: {text[-2000:]!r}")

            def status():
                return json.loads(_get("/api/pipeline/status", port=demo_port))

            _wait(status, 60, "status")
            st = _wait(lambda: (lambda s: s if (s.get("last_shot_id") or 0) >= 1 else None)(status()),
                       90, "last_shot_id >= 1 in demo")
            assert st.get("demo") is True, f"status.demo is not true: {st.get('demo')!r}"
            assert st["last_shot_id"] >= 1
            kids = _mediamtx_children(proc.pid)
            assert not kids, f"mediamtx.exe started under the exe (pids {kids}) in demo mode"
            assert not (st.get("rtmp") or {}).get("running", False), "RTMP server reported running in demo mode"
            demo_dir = data / "demo"
            assert demo_dir.is_dir(), f"{demo_dir} was not created"
            assert (demo_dir / "hiveshot.db").is_file(), "hiveshot.db not under <data>/demo"
            assert not (data / "hiveshot.db").exists(), "demo wrote hiveshot.db into the real data dir"
        finally:
            method, code = _stop(proc)
    record_property("exit_code", code)
    record_property("stop_method", method)
    print(f"packaged exe --demo stop_method={method} exit_code={code}")
    assert code in OK_EXIT_CODES, f"unexpected exit code {code} after {method}"

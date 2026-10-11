"""Tiny stdlib stub server: serves ui/ statically plus canned JSON for docs/api.md endpoints.

Not a test module (no test_ prefix). Used by test_ui_static.py and for manual checks:
    python tests/ui_stub_server.py [port]
"""
from __future__ import annotations

import json
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

UI_DIR = Path(__file__).resolve().parents[1] / "ui"

CONFIG = {
    "sources": [{"cam_id": "cam0", "kind": "file", "target": "x.mp4", "width": 1920, "height": 1080,
                 "fps_hint": 60, "backend": "auto", "loop": True, "realtime": True},
                {"cam_id": "cam1", "kind": "rtmp", "target": "cam1", "width": 1920, "height": 1080,
                 "fps_hint": 60, "backend": "auto", "loop": False, "realtime": True}],
    "calibration_path": "data/calibration.json", "alliance": "red", "hive_up_cell": "audience",
    "robot": {"length": 18, "width": 18, "height": 18, "launch_exit_height": 12},
    "burst_gap_s": 1.5, "settle_time_s": 0.75,
    "detector": {"min_radius_px": 4, "max_radius_px": 60, "pollen_hsv": [[0, 0, 0], [1, 1, 1]],
                 "nectar_hsv": [[0, 0, 0], [1, 1, 1]], "motion_thresh": 25},
    "preview_fps": 15,
    "session_name_template": "Practice {date} {time}",
    "profiles": {"arducam_1080p90": {"width": 1920, "height": 1080, "fps_hint": 90, "backend": "auto"}},
}
SHOT = {"shot_id": 1, "t_launch": 1.0, "burst_id": 1, "burst_index": 1, "ball_type": "pollen",
        "result": "made", "exit_speed_ips": 300.0, "exit_speed_mps": 7.62, "launch_angle_deg": 55.0,
        "launch_azimuth_deg": 90.0, "apex_z_in": 70.0, "equation": "z = -0.01 s^2 + 1.4 s + 12 (in)",
        "clip_url": None, "dropped_during_flight": 2}
FULL_SHOT = dict(SHOT, track=[{"t": 0.1 * i, "x": 0.0, "y": 10.0 * i, "z": 12 + 15 * i - i * i}
                              for i in range(8)],
                 parabola={"a": -0.01, "b": 1.4, "c": 12.0, "rmse_in": 0.4},
                 launch_point=[0.0, 0.0, 12.0], dropped_during_flight=2,
                 drag={"k_per_in": 0.000123456789, "rmse_in": 0.3456})
UNKNOWN_SHOT = dict(SHOT, shot_id=2, result="unknown", exit_speed_ips=None, exit_speed_mps=None,
                    launch_angle_deg=None, launch_azimuth_deg=None, apex_z_in=None, equation=None,
                    dropped_during_flight=0)
FULL_UNKNOWN_SHOT = dict(UNKNOWN_SHOT, track=[], parabola=None, drag=None, launch_point=None)
# Mirrors hiveshot.calib_targets.field_reference_points() (names and approximate xyz, inches).
CALIB_POINTS = [
    ("Red HIVE up-CELL opening, high-left corner", [-22.75, 20.73, 65.6]),
    ("Red HIVE up-CELL opening, high-right corner", [-2.75, 20.73, 65.6]),
    ("Red HIVE up-CELL opening, low-right corner", [-2.75, 27.76, 53.5]),
    ("Red HIVE up-CELL opening, low-left corner", [-22.75, 27.76, 53.5]),
    ("HIVE frame top corner (-X, +Y)", [-24.73, 19.48, 63.95]),
    ("HIVE frame top corner (+X, +Y)", [24.73, 19.48, 63.95]),
    ("HIVE frame top corner (-X, -Y)", [-24.73, -19.48, 63.95]),
    ("HIVE frame top corner (+X, -Y)", [24.73, -19.48, 63.95]),
]
CROSSCHECK = {"max_error_in": 1.6, "points": [
    {"name": n, "xyz_measured": [round(v + 0.2, 2) for v in xyz], "xyz_expected": xyz,
     "error_in": 0.35 if i < 7 else 1.6} for i, (n, xyz) in enumerate(CALIB_POINTS)]}
PDF_BYTES = b"%PDF-1.4\n% stub checkerboard\n%%EOF\n"
STATS = {"session_id": "s1", "shots": 1, "made": 1, "bounce_out": 0, "miss": 0, "unknown": 0,
         "make_rate": 1.0, "by_ball_type": {"pollen": {"shots": 1, "made": 1}},
         "failure_order_hist": {str(i): 0 for i in range(1, 6)},
         "bounce_out_order_hist": {str(i): 0 for i in range(1, 6)},
         "tips": 0, "mean_exit_speed_ips": 300.0, "mean_launch_angle_deg": 55.0}
ROUTES = {
    # deliberately NOT newest-first: the UI must order by started_at itself
    "/api/sessions": [{"session_id": "s1", "name": "n", "started_at": 1, "ended_at": None, "shots": 2, "made": 1},
                      {"session_id": "s2", "name": "newer", "started_at": 5, "ended_at": 9, "shots": 0, "made": 0},
                      {"session_id": "s0", "name": "older", "started_at": 0, "ended_at": 1, "shots": 0, "made": 0}],
    "/api/sessions/s1/stats": STATS,
    "/api/sessions/s1/shots": [SHOT, UNKNOWN_SHOT],
    "/api/sessions/s1/tips": [{"t": 2.0, "alliance": "red", "new_up_cell": "far", "caused_by_shot_id": 1}],
    "/api/shots/1": FULL_SHOT,
    "/api/shots/2": FULL_UNKNOWN_SHOT,
    "/api/config": CONFIG,
    "/api/calib/points": [{"name": n, "xyz": xyz} for n, xyz in CALIB_POINTS],
    "/api/setup/status": {
        "cameras_detected": [{"index": 0, "width": 1920, "height": 1080, "fps": 90},
                             {"index": 1, "width": 1920, "height": 1080, "fps": 90}],
        "sources_configured": False, "calibration_loaded": False,
        "tags_seen": {"cam0": [100, 101], "cam1": []}, "pipeline_running": False,
        "recommendations": ["Plug both cameras into USB 3 ports.", "Tape the tags flat on the HIVE frame corners."]},
    "/api/calib/tags": [{"id": 100 + i, "size_in": 4.0, "name": n, "xyz_center": [0, 0, 0], "corners_xyz": []}
                        for i, n in enumerate(["frame top corner (-X,+Y)", "frame top corner (+X,+Y)",
                                               "frame top corner (-X,-Y)", "frame top corner (+X,-Y)"])],
    "/api/devices": [{"index": 0, "width": 1280, "height": 720, "fps": 30}],
    "/api/pipeline/status": {"running": False, "detector_fps": 0, "last_shot_id": None,
                             "cameras": {"cam0": {"fps": 60.0, "dropped": 3, "is_alive": True, "ended": False}},
                             "session_id": "s1", "calibration_mismatch": {},
                             "hive_state_source": "tags",
                             "warnings": ["stub warning: cam1 has no frames yet"], "calibration_loaded": False,
                             "rtmp": {"available": True, "running": True,
                                      "urls": {"cam0": "rtmp://127.0.0.1:1935/cam0",
                                               "cam1": "rtmp://127.0.0.1:1935/cam1"}},
                             "hive_state": {"alliance": "red", "up_cell": "audience"}},
    "/api/calib": {"cameras": {}},
    "/api/field/geometry": {"field_size": 144.0, "bounds": {"min": [-72, -72, 0], "max": [72, 72, 100]},
                            "hives": {}, "wireframe": [[[0, 0, 0], [0, 0, 10]]], "cell_extent": 12.04},
}


# Canned WebSocket payloads (this stdlib stub has no WS endpoint; tests/manual checks inject them).
WS_MESSAGES = [
    {"type": "shot_updated", "shot": dict(SHOT, burst_id=2, burst_index=1, session_id="s1"), "stats": STATS},
    {"type": "tip", "tip": {"t": 3.0, "alliance": "red", "new_up_cell": "audience", "caused_by_shot_id": 1}},
    {"type": "status", "running": True, "session_id": None, "calibration_mismatch": {"cam0": "1920x1080 vs 1280x720"}},
]


# POST /api/demo/start|stop return 200 at once but, like the real backend, status.demo only flips
# DEMO_DELAY_S seconds later (the pipeline is still switching until then).
DEMO_DELAY_S = 2.0
DEMO_STATE = {"on": False, "target": False, "at": 0.0}


def demo_now() -> bool:
    if time.monotonic() >= DEMO_STATE["at"]:
        DEMO_STATE["on"] = DEMO_STATE["target"]
    return DEMO_STATE["on"]
POST_ROUTES = {
    "/api/demo/start": {"ok": True, "session_id": "s1"},
    "/api/demo/stop": {"ok": True},
    "/api/calib/crosscheck": CROSSCHECK,
    "/api/calib/auto_all": {"cameras": {"cam0": {"rmse_in": 0.4, "tags_used": [100, 101, 102], "reprojection_px": 0.8},
                                        "cam1": {"error": "Only 1 tag visible; need at least 2."}},
                            "max_error_in": 0.6,
                            "warning": "Stub: using the HIVE's own tags is less accurate than the printed sheet."},
    "/api/detector/sample": {"ball_type": "pollen", "hsv": [[12, 90, 90], [40, 255, 255]]},
    "/api/calib/hive_tags/learn": {"learned_ids": [30, 31, 32, 33, 34, 35], "missing_ids": [36, 37],
                                   "visible_per_camera": {"cam0": 8, "cam1": 7}, "max_residual_in": 0.35, "up_cell_error_in": 0.7},
    "/api/pipeline/start": {"ok": True},
    "/api/pipeline/stop": {"ok": True},
    "/api/sessions": {"session_id": "s9"},
}


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        n = int(self.headers.get("Content-Length") or 0)
        if n:
            self.rfile.read(n)
        if path in ("/api/demo/start", "/api/demo/stop"):
            demo_now()
            DEMO_STATE["target"] = path.endswith("start")
            DEMO_STATE["at"] = time.monotonic() + DEMO_DELAY_S
        if path in POST_ROUTES:
            body = json.dumps(POST_ROUTES[path]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_PUT(self):
        n = int(self.headers.get("Content-Length") or 0)
        if self.path.split("?", 1)[0] == "/api/config":
            body = json.dumps(json.loads(self.rfile.read(n) or b"{}")).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/api/calib/checkerboard.pdf", "/api/calib/tags.pdf"):
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Disposition", 'attachment; filename="checkerboard_10x7_1in.pdf"')
            self.send_header("Content-Length", str(len(PDF_BYTES)))
            self.end_headers()
            self.wfile.write(PDF_BYTES)
            return
        if path in ROUTES:
            payload = ROUTES[path]
            if path == "/api/pipeline/status":
                payload = dict(payload, demo=demo_now())
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


def start(port: int = 0) -> tuple[ThreadingHTTPServer, threading.Thread]:
    srv = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=str(UI_DIR)))
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    return srv, th


if __name__ == "__main__":
    s, _ = start(int(sys.argv[1]) if len(sys.argv) > 1 else 8766)
    print("stub on", s.server_address)
    threading.Event().wait()

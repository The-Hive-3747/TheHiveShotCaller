"""Tiny pass-through proxy so the real UI can be loaded against a real backend WITHOUT the app's own
GET /api/setup/status (which probes camera indexes 0..5 and would open the laptop webcam).
/api/setup/status is answered here from /api/pipeline/status + /api/config (same fields, no device probe).
usage: uiproxy.py <listen_port> <backend_port>
"""
import json, sys, threading, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LP, BP = int(sys.argv[1]), int(sys.argv[2])
B = f"http://127.0.0.1:{BP}"


def fetch(path, method="GET", body=None, headers=None):
    req = urllib.request.Request(B + path, data=body, method=method, headers=headers or {})
    try:
        r = urllib.request.urlopen(req, timeout=120)
        return r.status, r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers.get("Content-Type", "")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _do(self, method):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else None
        if self.path.startswith("/api/setup/status"):
            _, st, _ = fetch("/api/pipeline/status")
            _, cf, _ = fetch("/api/config")
            st, cf = json.loads(st), json.loads(cf)
            out = {"cameras_detected": [], "sources_configured": len(cf["sources"]) >= 2,
                   "calibration_loaded": st["calibration_loaded"], "calibration_source": st["calibration_source"],
                   "intrinsics_default": st["intrinsics_default"], "tags_seen": {}, "tags_roll": {},
                   "pipeline_running": st["running"], "recommendations": []}
            code, raw, ct = 200, json.dumps(out).encode(), "application/json"
        else:
            code, raw, ct = fetch(self.path, method, body, {"Content-Type": self.headers.get("Content-Type", "application/json")})
        self.send_response(code)
        self.send_header("Content-Type", ct or "application/octet-stream")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self._do("GET")

    def do_POST(self):
        self._do("POST")

    def do_PUT(self):
        self._do("PUT")


ThreadingHTTPServer(("127.0.0.1", LP), H).serve_forever()

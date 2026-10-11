import json, time, urllib.request, urllib.error
class Api:
    def __init__(self, port):
        self.base = f"http://127.0.0.1:{port}"; self.log = []
    def call(self, method, path, body=None, timeout=300):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={"Content-Type": "application/json"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read(); ct = r.headers.get("Content-Type", ""); code = r.status
        except urllib.error.HTTPError as e:
            raw, ct, code = e.read(), e.headers.get("Content-Type", ""), e.code
        dt = time.time() - t0
        out = json.loads(raw) if "json" in ct else {"_bytes": len(raw), "_ct": ct}
        self.log.append((method, path, code, round(dt, 2)))
        return code, out, dt
    def ok(self, *a, **k):
        code, out, dt = self.call(*a, **k)
        if code >= 400: raise RuntimeError(f"{a[:2]} -> {code} {out}")
        return out

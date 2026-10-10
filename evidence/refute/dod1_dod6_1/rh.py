import json, urllib.request, urllib.error, sys, time
def call(method, port, path, body=None, timeout=60):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read())
        except Exception: return e.code, None
def wait_up(port, n=60):
    for _ in range(n):
        try:
            call("GET", port, "/api/config", timeout=2); return True
        except Exception: time.sleep(0.5)
    return False
def cams(port):
    s, st = call("GET", port, "/api/pipeline/status")
    return st
def brief(st):
    return {"running": st["running"], "rtmp": st["rtmp"]["running"],
            "cams": {k: {x: v.get(x) for x in ("fps","frames_read","is_alive","last_error","reconnects","ended")} for k, v in st["cameras"].items()},
            "last_error": st.get("last_error"), "calib_mismatch": st.get("calibration_mismatch")}

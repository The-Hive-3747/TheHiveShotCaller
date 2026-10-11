import sys, json, urllib.request, urllib.error
port, method, path = sys.argv[1], sys.argv[2], sys.argv[3]
body = json.loads(sys.argv[4]) if len(sys.argv) > 4 else None
req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=None if body is None else json.dumps(body).encode(), method=method, headers={"Content-Type": "application/json"})
try:
    r = urllib.request.urlopen(req, timeout=120); code = r.status; raw = r.read()
except urllib.error.HTTPError as e:
    code = e.code; raw = e.read()
try: print(code, json.dumps(json.loads(raw))[:int(sys.argv[5]) if len(sys.argv)>5 else 3000])
except Exception: print(code, len(raw))

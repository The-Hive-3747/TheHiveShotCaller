"""wait until whole-machine CPU averaged over 10 s is below a threshold (default 15 %), max 600 s; prints the last value."""
import ctypes, sys, time
from ctypes import wintypes
class FT(ctypes.Structure): _fields_ = [("lo", wintypes.DWORD), ("hi", wintypes.DWORD)]
def t():
    i, k, u = FT(), FT(), FT(); ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(i), ctypes.byref(k), ctypes.byref(u))
    f = lambda x: (x.hi << 32) | x.lo
    return f(i), f(k), f(u)
thr = float(sys.argv[1]) if len(sys.argv) > 1 else 15.0
t0 = time.time(); load = 100
while time.time() - t0 < float(sys.argv[2] if len(sys.argv) > 2 else 600):
    a = t(); time.sleep(10); b = t()
    tot = (b[1]-a[1]) + (b[2]-a[2]); load = 100.0 * (tot - (b[0]-a[0])) / tot
    if load < thr: break
print(f"idle-wait: cpu={load:.0f}% after {time.time()-t0:.0f}s")

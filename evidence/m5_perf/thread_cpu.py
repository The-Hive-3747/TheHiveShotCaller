"""Per-native-thread CPU time of this process (Windows): thread_cpu_report() -> list of (cpu_s, tid, name)."""
import ctypes, ctypes.wintypes as w, os, threading
k = ctypes.WinDLL("kernel32", use_last_error=True)
TH32CS_SNAPTHREAD = 0x4
class THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", w.DWORD), ("cntUsage", w.DWORD), ("th32ThreadID", w.DWORD), ("th32OwnerProcessID", w.DWORD), ("tpBasePri", w.LONG), ("tpDeltaPri", w.LONG), ("dwFlags", w.DWORD)]
k.CreateToolhelp32Snapshot.restype = w.HANDLE
k.OpenThread.restype = w.HANDLE
k.OpenThread.argtypes = [w.DWORD, w.BOOL, w.DWORD]
k.GetThreadTimes.argtypes = [w.HANDLE, ctypes.POINTER(w.FILETIME), ctypes.POINTER(w.FILETIME), ctypes.POINTER(w.FILETIME), ctypes.POINTER(w.FILETIME)]
k.CloseHandle.argtypes = [w.HANDLE]
def _ft(f): return ((f.dwHighDateTime << 32) | f.dwLowDateTime) / 1e7
def snapshot():
    names = {t.native_id: t.name for t in threading.enumerate()}
    snap = k.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    e = THREADENTRY32(); e.dwSize = ctypes.sizeof(e)
    out = {}
    ok = k.Thread32First(snap, ctypes.byref(e))
    while ok:
        if e.th32OwnerProcessID == os.getpid():
            h = k.OpenThread(0x0040, False, e.th32ThreadID)   # THREAD_QUERY_LIMITED_INFORMATION
            if h:
                c, x, kt, ut = w.FILETIME(), w.FILETIME(), w.FILETIME(), w.FILETIME()
                if k.GetThreadTimes(h, ctypes.byref(c), ctypes.byref(x), ctypes.byref(kt), ctypes.byref(ut)):
                    out[e.th32ThreadID] = (_ft(kt) + _ft(ut), names.get(e.th32ThreadID, "native"))
                k.CloseHandle(h)
        ok = k.Thread32Next(snap, ctypes.byref(e))
    k.CloseHandle(snap)
    return out

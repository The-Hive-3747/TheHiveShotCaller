import ctypes, ctypes.wintypes as w
k = ctypes.WinDLL("kernel32", use_last_error=True)
k.GetCurrentProcess.restype = w.HANDLE
k.SetPriorityClass.argtypes = [w.HANDLE, w.DWORD]
k.SetProcessInformation.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
class PPT(ctypes.Structure):
    _fields_ = [("Version", w.ULONG), ("ControlMask", w.ULONG), ("StateMask", w.ULONG)]
def no_eco():
    s = PPT(1, 0x1, 0x0)
    ok = k.SetProcessInformation(k.GetCurrentProcess(), 4, ctypes.byref(s), ctypes.sizeof(s))
    return ok or ctypes.get_last_error()
def prio(cls):
    return k.SetPriorityClass(k.GetCurrentProcess(), cls)

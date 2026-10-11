import sys, time, threading
sys.path.insert(0, ".")
mode = sys.argv[2]
stop = [False]
def sleeper():
    while not stop[0]: time.sleep(0.001)
def evwait():
    ev = threading.Event()
    while not stop[0]: ev.wait(0.001)
def spin():
    while not stop[0]: pass
def sleep0():
    while not stop[0]: time.sleep(0)
fn = {"sleep1ms": sleeper, "evwait": evwait, "spin": spin, "sleep0": sleep0, "none": None}[mode]
if fn: threading.Thread(target=fn, daemon=True).start()
sys.argv = ["x", sys.argv[1], "base"]
exec(open("evidence/m5_perf/rt_exp2.py").read())
stop[0] = True

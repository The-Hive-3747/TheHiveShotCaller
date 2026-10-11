import sys, time
t_begin = time.perf_counter()
exec(open("evidence/m5_perf/rt_run.py").read())
print("PROCESS cpu %.1f s  wall %.1f s" % (time.process_time(), time.perf_counter() - t_begin))

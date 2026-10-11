"""Experiment runner: python rt_exp.py <fixture> <variant> ; variants: base, notags, noclips, norecon"""
import sys
sys.path.insert(0, ".")
fx, var = sys.argv[1], sys.argv[2]
from hiveshot import pipeline as P
if var == "notags":
    P.Pipeline._tag_tick = lambda self: None
if var == "norecon":
    P.Pipeline._recon_cycle = lambda self, final=False: None
sys.argv = ["x", fx] + (["--noclips"] if var == "noclips" else [])
exec(open("evidence/m5_perf/rt_run.py").read())

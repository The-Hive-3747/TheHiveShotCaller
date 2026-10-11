#!/bin/bash
# usage: dod2_3_2_load.sh <n_burners> <fixture> <mode> <suffix>   (starts n busy-loop python processes, runs one app run, kills them)
cd /c/Users/3747h/Documents/HiveShotTracker
SP="C:/Users/3747h/AppData/Local/Temp/claude/C--Users-3747h-Documents-HiveShotTracker/386da1de-9207-4304-8c4f-9284e5732d29/scratchpad/fx"
D=evidence/refute/dod2_3_2
PY=.venv/Scripts/python.exe
N=$1; name=$2; mode=$3; suf=$4
tag=${name}_${mode}_${suf}_load${N}
pids=()
for i in $(seq 1 $N); do $PY -c "while True: pass" & pids+=($!); done
sleep 3
{ echo "RUN $tag with $N busy-loop burners"; $PY evidence/refute/dod2_3_2_run.py $SP/$name 8792 $mode $D/$tag.json 2>&1; } > $D/$tag.txt
for p in "${pids[@]}"; do taskkill //F //T //PID $p > /dev/null 2>&1; done
cat $D/$tag.txt

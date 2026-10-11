#!/bin/bash
# args: "fixture mode suffix [--stress]" ... ; sequential, 20 s gap then wait for machine CPU < 15 %
cd /c/Users/3747h/Documents/HiveShotTracker; export HS_ROOT="${HS_ROOT:-C:/Users/3747h/Documents/HiveShotTracker}"
SP="C:/Users/3747h/AppData/Local/Temp/claude/C--Users-3747h-Documents-HiveShotTracker/386da1de-9207-4304-8c4f-9284e5732d29/scratchpad/fx"
D=${D:-evidence/refute/dod2_3_2}
PY=.venv/Scripts/python.exe
run() {
  name=$1; mode=$2; suf=$3; shift 3
  tag=${name}_${mode}_${suf}
  sleep 20
  $PY evidence/refute/dod2_3_2_waitidle.py 15 60 > $D/$tag.idle 2>&1
  { echo "RUN $tag $(cat $D/$tag.idle)"; $PY evidence/refute/dod2_3_2_run.py $SP/$name 8791 $mode $D/$tag.json "$@" 2>&1; } > $D/$tag.txt
  cat $D/$tag.txt
}
for l in "$@"; do run $l; done
echo BATCH_DONE

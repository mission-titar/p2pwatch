#!/usr/bin/env bash
# launch.sh <arm> <model> <task>...: each task once: setup, run, measure, fix to green; three at a time.
S=$(cd "$(dirname "$0")" && pwd); arm=$1; model=$2; shift 2
for t in "$@"; do
  ( bash "$S/setup.sh" "$arm" "$t" 1 && bash "$S/run_one.sh" "$arm" "$t" 1 "$model" && bash "$S/measure.sh" "$arm" "$t" 1 >/dev/null && bash "$S/fix_one.sh" "$arm" "$t" 1 "$model" ) > "$S/launch-$arm-$t.log" 2>&1 &
  while [ "$(jobs -rp | wc -l)" -ge 3 ]; do sleep 20; done
done
wait; echo "done $arm"

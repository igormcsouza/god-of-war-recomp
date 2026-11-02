#!/usr/bin/env bash
# Measures the FPS of a runner with GOW_FPS=1 ([gow-fps] lines) after a warm-up.
if [ $# -lt 4 ]; then
  echo "Usage: $0 <runner> <elf> <iso> <seconds> [warmup=20]" >&2
  exit 2
fi
runner=$1; elf=$2; iso=$3; secs=$4; warm=${5:-20}
[ -e "$runner" ] && runner=$(readlink -f "$runner")
elf=$(readlink -f "$elf"); iso=$(readlink -f "$iso")
cd "$(dirname "$elf")" || exit 1
log=/tmp/measure_fps_$$.log
GOW_FPS=1 GOW_ISO="$iso" GOW_AUDIO=0 GOW_SKIP_FMV=1 timeout "$secs" "$runner" "$elf" 2> "$log"
if ! grep -q '\[gow-fps\]' "$log"; then
  echo "no samples, last 20 log lines:"
  tail -20 "$log"
else
  grep '\[gow-fps\]' "$log" | LC_ALL=C awk -v w="$warm" '
  BEGIN { split("game shown display", k, " ") }
  {
    if (!match($0, / t=[0-9.]+/)) next
    if (substr($0, RSTART + 3, RLENGTH - 3) + 0 < w) next
    for (i = 1; i <= 3; i++) {
      if (match($0, " " k[i] "=[0-9.]+")) {
        v = substr($0, RSTART + length(k[i]) + 2, RLENGTH - length(k[i]) - 2) + 0
        n[i]++; s[i] += v
        if (n[i] == 1 || v < m[i]) m[i] = v
      }
    }
  }
  END {
    for (i = 1; i <= 3; i++) {
      if (n[i]) { printf "%-9s samples=%d avg=%.1f min=%.1f\n", k[i], n[i], s[i] / n[i], m[i] }
      else { printf "%-9s samples=0\n", k[i] }
    }
  }'
fi
echo "full log: $log"

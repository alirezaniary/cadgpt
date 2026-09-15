#!/usr/bin/env bash
set -euo pipefail

if [[ ! -x "$(dirname "$0")/.venv/bin/python" ]]; then
  echo "missing tools/paddleocr/.venv; follow tools/paddleocr/README.md" >&2
  exit 2
fi

# Keep host-side preprocessing bounded while inference runs on Paddle CUDA.
cpu_count="$(nproc)"
if (( cpu_count > 4 )); then
  cpu_list="0-3"
else
  cpu_list="0-$((cpu_count - 1))"
fi
exec timeout --signal=TERM --kill-after=15s 300s \
  taskset --cpu-list "$cpu_list" nice -n 15 ionice -c 3 \
  "$(dirname "$0")/.venv/bin/python" "$(dirname "$0")/run_safe.py" "$@"

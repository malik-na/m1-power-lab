#!/usr/bin/env bash
set -Eeuo pipefail
unset M1LAB_SLEEP_LID_INHIBITOR_HELD

if [[ ${M1LAB_INHIBIT_SLEEP:-0} == 1 ]]; then
  inhibitor=$(command -v systemd-inhibit) || {
    echo "M1LAB_INHIBIT_SLEEP=1 but systemd-inhibit is unavailable" >&2
    exit 78
  }
  export M1LAB_SLEEP_LID_INHIBITOR_HELD=1
  exec "$inhibitor" \
    --what=sleep:idle:handle-lid-switch \
    --who="M1 Power Lab" \
    --why="bounded lab service is enabled" \
    --mode=block \
    "$@"
fi

if [[ ${M1LAB_INHIBIT_SLEEP:-0} != 0 ]]; then
  echo "M1LAB_INHIBIT_SLEEP must be 0 or 1" >&2
  exit 78
fi

exec "$@"

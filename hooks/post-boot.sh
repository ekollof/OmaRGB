#!/bin/bash
# Firmware drops lighting on power loss, and a theme change is not part of login.
set -euo pipefail

omargb="$HOME/.local/bin/omargb"
[[ -x $omargb ]] || exit 0

for _ in $(seq 1 30); do
  set +e
  "$omargb" apply
  status=$?
  set -e
  if (( status == 0 )); then
    exit 0
  fi
  sleep 1
done
exit 0

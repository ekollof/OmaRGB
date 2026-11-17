#!/bin/bash
set -euo pipefail

root=$(cd -- "$(dirname -- "$0")" && pwd)
# shellcheck disable=SC1091
source "$root/share/omarchy-ui.sh"
omargb_banner

bin_dir="$HOME/.local/bin"
share_dir="$HOME/.local/share/omargb"
state_dir="$HOME/.local/state/omargb"
hook_dir="$HOME/.config/omarchy/hooks"
unit_dir="$HOME/.config/systemd/user"
state_file="$state_dir/install.json"

systemctl --user disable --now omargb-theme.path >/dev/null 2>&1 || true
rm -f "$unit_dir/omargb-apply.service" "$unit_dir/omargb-theme.path"
rm -f "$hook_dir/theme-set.d/omargb" "$hook_dir/post-boot.d/omargb"
rm -f "$HOME/.config/uwsm/env.d/90-omargb"
rm -f "$bin_dir/omargb"
rm -rf "$share_dir/shims"
rm -f "$share_dir/src"

if [[ -f $state_file ]]; then
  python3 - "$state_file" "$hook_dir" "$state_dir/parked-hooks" << 'PY'
import json
import subprocess
import sys
from pathlib import Path

state = json.loads(Path(sys.argv[1]).read_text())
hook_dir = Path(sys.argv[2])
park_dir = Path(sys.argv[3])
for relative in state.get("disabled_hooks", []):
    original = hook_dir / relative
    parked = park_dir / relative
    legacy = hook_dir / f"{relative}.disabled-by-omargb"
    source = parked if parked.is_file() else legacy
    if source.is_file() and not original.exists():
        original.parent.mkdir(parents=True, exist_ok=True)
        source.rename(original)
for unit in state.get("disabled_units", []):
    subprocess.run(["systemctl", "--user", "enable", "--now", unit], check=False)
PY
  rm -f "$state_file"
fi

systemctl --user daemon-reload
echo
omargb_card "OmaRGB" "" "• Removed the hooks, the watcher, and the shims."
echo
omargb_ok "Done"
omargb_muted "A new login drops the shim directory from PATH."

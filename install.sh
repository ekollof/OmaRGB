#!/bin/bash
# Install OmaRGB into the current user's Omarchy session.
set -euo pipefail

root=$(cd -- "$(dirname -- "$0")" && pwd)
bin_dir="$HOME/.local/bin"
share_dir="$HOME/.local/share/omargb"
state_dir="$HOME/.local/state/omargb"
hook_dir="$HOME/.config/omarchy/hooks"
unit_dir="$HOME/.config/systemd/user"
env_dir="$HOME/.config/uwsm/env.d"
state_file="$state_dir/install.json"

mkdir -p "$bin_dir" "$share_dir/shims" "$state_dir" \
  "$hook_dir/theme-set.d" "$hook_dir/post-boot.d" "$unit_dir" "$env_dir"

ln -sfn "$root" "$share_dir/src"
ln -sfn "$root/bin/omargb" "$bin_dir/omargb"
chmod 755 "$root/bin/omargb" "$root/hooks/"*.sh "$root/shims/"*

install -m 755 "$root/hooks/theme-set.sh" "$hook_dir/theme-set.d/omargb"
install -m 755 "$root/hooks/post-boot.sh" "$hook_dir/post-boot.d/omargb"
for shim in "$root/shims/"*; do
  install -m 755 "$shim" "$share_dir/shims/$(basename "$shim")"
done

install -m 644 "$root/systemd/omargb-apply.service" "$unit_dir/omargb-apply.service"
install -m 644 "$root/systemd/omargb-theme.path" "$unit_dir/omargb-theme.path"

cat > "$env_dir/90-omargb" << 'EOF'
# Put OmaRGB ahead of Omarchy's own RGB painters.
case ":$PATH:" in
  *":$HOME/.local/share/omargb/shims:"*) ;;
  *) PATH="$HOME/.local/share/omargb/shims:$PATH" ;;
esac
export PATH
EOF

# The earlier K08-only hook paints the same keyboard. Step it aside.
disabled=()
for hook in theme-set.d/vanguard-k08-rgb post-boot.d/vanguard-k08-rgb; do
  source_hook="$hook_dir/$hook"
  if [[ -f $source_hook && ! -f $source_hook.disabled-by-omargb ]]; then
    mv "$source_hook" "$source_hook.disabled-by-omargb"
    disabled+=("$hook")
  fi
done

disabled_units=()
if systemctl --user is-enabled vanguard-k08-theme-watch.service >/dev/null 2>&1; then
  systemctl --user disable --now vanguard-k08-theme-watch.service
  disabled_units+=("vanguard-k08-theme-watch.service")
fi

python3 - "$state_file" "${disabled[@]+"${disabled[@]}"}" -- "${disabled_units[@]+"${disabled_units[@]}"}" << 'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
args = sys.argv[2:]
split = args.index("--")
previous = {}
if path.is_file():
    previous = json.loads(path.read_text())
hooks = list(dict.fromkeys([*previous.get("disabled_hooks", []), *args[:split]]))
units = list(dict.fromkeys([*previous.get("disabled_units", []), *args[split + 1:]]))
path.write_text(json.dumps({"disabled_hooks": hooks, "disabled_units": units}, indent=2) + "\n")
PY

systemctl --user daemon-reload
systemctl --user enable --now omargb-theme.path

echo "OmaRGB installed."
echo "Theme changes, wallpaper palette updates, and login call: omargb apply"
echo "The shim directory is prepended to PATH at the next graphical login."
echo "Until then, Omarchy may paint first and the theme hook corrects it."

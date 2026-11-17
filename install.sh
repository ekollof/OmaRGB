#!/bin/bash
# Install OmaRGB into the current user's Omarchy session.
set -euo pipefail

root=$(cd -- "$(dirname -- "$0")" && pwd)
# shellcheck disable=SC1091
source "$root/share/omarchy-ui.sh"
omargb_update_checkout "$root" "$root/install.sh" "$@"
omargb_banner

bin_dir="$HOME/.local/bin"
share_dir="$HOME/.local/share/omargb"
state_dir="$HOME/.local/state/omargb"
hook_dir="$HOME/.config/omarchy/hooks"
unit_dir="$HOME/.config/systemd/user"
env_dir="$HOME/.config/uwsm/env.d"
state_file="$state_dir/install.json"
updating=0
if [[ -L $bin_dir/omargb || -f $state_file ]]; then
  updating=1
fi

mkdir -p "$bin_dir" "$share_dir" "$state_dir" \
  "$hook_dir/theme-set.d" "$hook_dir/post-boot.d" "$unit_dir" "$env_dir"

# The command and the device database stay linked to this checkout, so a
# later edit is what `omargb` runs. Hooks, shims, and units are copies, so
# each run replaces them and drops a copy this tree no longer ships.
ln -sfn "$root" "$share_dir/src"
ln -sfn "$root/bin/omargb" "$bin_dir/omargb"
chmod 755 "$root/bin/omargb" "$root/hooks/"*.sh "$root/shims/"*

rm -rf "$share_dir/shims"
mkdir -p "$share_dir/shims"
for shim in "$root/shims/"*; do
  [[ -f $shim ]] || continue
  install -m 755 "$shim" "$share_dir/shims/$(basename "$shim")"
done

install -m 755 "$root/hooks/theme-set.sh" "$hook_dir/theme-set.d/omargb"
install -m 755 "$root/hooks/post-boot.sh" "$hook_dir/post-boot.d/omargb"
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

installed_now=(
  "$bin_dir/omargb"
  "$share_dir/src"
  "$hook_dir/theme-set.d/omargb"
  "$hook_dir/post-boot.d/omargb"
  "$unit_dir/omargb-apply.service"
  "$unit_dir/omargb-theme.path"
  "$env_dir/90-omargb"
)
for shim in "$share_dir/shims/"*; do
  [[ -e $shim ]] || continue
  installed_now+=("$shim")
done

python3 - "$state_file" \
  --hooks ${disabled[@]+"${disabled[@]}"} \
  --units ${disabled_units[@]+"${disabled_units[@]}"} \
  --installed "${installed_now[@]}" << 'PY'
import json
import subprocess
import sys
from pathlib import Path

path = Path(sys.argv[1])
args = sys.argv[2:]

def take(flag: str) -> list[str]:
    if flag not in args:
        return []
    values = []
    for item in args[args.index(flag) + 1:]:
        if item.startswith("--"):
            break
        values.append(item)
    return values

previous = {}
if path.is_file():
    previous = json.loads(path.read_text())
hooks = list(dict.fromkeys([*previous.get("disabled_hooks", []), *take("--hooks")]))
units = list(dict.fromkeys([*previous.get("disabled_units", []), *take("--units")]))
installed = take("--installed")
home = Path.home()
owned = (
    home / ".local/share/omargb",
    home / ".local/bin",
    home / ".config/omarchy/hooks",
    home / ".config/systemd/user",
    home / ".config/uwsm/env.d",
)
fresh = set(installed)
for old in previous.get("installed", []):
    if old in fresh:
        continue
    stale = Path(old)
    if not stale.is_absolute():
        continue
    if not any(stale == prefix or prefix in stale.parents for prefix in owned):
        continue
    if stale.is_symlink() or stale.is_file():
        if stale.name.endswith((".service", ".path")):
            subprocess.run(["systemctl", "--user", "disable", "--now", stale.name], check=False)
        stale.unlink()
path.write_text(json.dumps(
    {"disabled_hooks": hooks, "disabled_units": units, "installed": installed},
    indent=2,
) + "\n")
PY

systemctl --user daemon-reload
systemctl --user enable --now omargb-theme.path

hardware=()
pkg_names=()
if [[ ${OMARGB_INSTALL_DEPS:-1} == 1 ]]; then
  deps_output=$(python3 - "$root" << 'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
from omargb.deps import report
from omargb.engines.openrgb import list_devices
from omargb.scan import scan

sys.stdout.write(report(scan(), list_devices()))
PY
)
  arch_pkgs=()
  aur_pkgs=()
  services=()
  udev_rules=()
  while IFS=$'\t' read -r kind a b; do
    [[ -n $kind ]] || continue
    case $kind in
      device) hardware+=("$a") ;;
      package)
        pkg_names+=("$b")
        if [[ $a == aur ]]; then aur_pkgs+=("$b"); else arch_pkgs+=("$b"); fi
        ;;
      service) services+=("$a") ;;
      udev) udev_rules+=("$a"$'\t'"$b") ;;
    esac
  done <<< "$deps_output"
  if (( ${#arch_pkgs[@]} )); then
    omargb_muted "Installing ${arch_pkgs[*]}"
    omarchy-pkg-add "${arch_pkgs[@]}"
  fi
  if (( ${#aur_pkgs[@]} )); then
    omargb_muted "Installing ${aur_pkgs[*]}"
    omarchy-pkg-aur-add "${aur_pkgs[@]}"
  fi
  for rule in "${udev_rules[@]+"${udev_rules[@]}"}"; do
    src="${OMARCHY_PATH:-/usr/share/omarchy}/${rule%%$'\t'*}"
    dest="${rule#*$'\t'}"
    if [[ -f $src && ! -f $dest ]]; then
      sudo install -m 644 "$src" "$dest"
    fi
  done
  for service in "${services[@]+"${services[@]}"}"; do
    if ! systemctl is-enabled --quiet "$service" || ! systemctl is-active --quiet "$service"; then
      sudo systemctl enable --now "$service"
    fi
  done
fi

if (( updating )); then
  summary="• Updated hooks, shims, and units from this checkout."
else
  summary="• Installed into this session."
fi
card_lines=(
  "$summary"
  "• The command and device database follow this checkout."
  "• A theme or palette change runs omargb apply."
)
if [[ ${OMARGB_INSTALL_DEPS:-1} == 1 ]]; then
  if (( ${#hardware[@]} )); then
    card_lines+=("• Hardware")
    for name in "${hardware[@]}"; do
      card_lines+=("  $name")
    done
  else
    card_lines+=("• No supported hardware is connected, so no painter packages were installed.")
  fi
  if (( ${#pkg_names[@]} )); then
    card_lines+=("• Painter packages")
    for name in "${pkg_names[@]}"; do
      card_lines+=("  $name")
    done
  fi
fi
echo
omargb_card "OmaRGB" "" "${card_lines[@]}"
echo
omargb_ok "Done"
omargb_muted "The shim directory is prepended to PATH at the next graphical login."
omargb_muted "Until then, Omarchy may paint first and the theme hook corrects it."

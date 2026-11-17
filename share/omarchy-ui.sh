# Omarchy console styling for the installer. Sourced, not executed.
# gum colours come from the active theme, the same way omarchy-restart-gum loads them.
# The status mark is the one omarchy-show-done prints.

omargb_refresh_gum() {
  local loader=/usr/bin/omarchy-restart-gum
  if [[ -r $loader ]]; then
    # shellcheck disable=SC1091
    source "$loader"
  fi
}

omargb_banner() {
  local logo="${OMARCHY_PATH:-/usr/share/omarchy}/logo.txt"
  omargb_refresh_gum
  if [[ -r $logo ]] && command -v gum >/dev/null 2>&1; then
    gum style --foreground 2 --padding "1 0" -- "$(<"$logo")" || true
  fi
}

omargb_card() {
  local columns=80
  if command -v gum >/dev/null 2>&1; then
    columns=$(tput cols 2>/dev/null || echo 80)
    if (( columns > 64 )); then columns=64; fi
    if (( columns < 42 )); then columns=42; fi
    gum style --border normal --padding "1 2" --width "$columns" -- "$@" || true
  else
    printf '%s\n' "$@"
  fi
}

omargb_ok() {
  printf '\033[32m● \033[0m%s\n' "$1"
}

omargb_muted() {
  if command -v gum >/dev/null 2>&1; then
    gum style --foreground 8 -- "$1" || true
  else
    printf '%s\n' "$1"
  fi
}

omargb_warn() {
  if command -v gum >/dev/null 2>&1; then
    gum style --foreground 3 -- "$1" || true
  else
    printf '%s\n' "$1" >&2
  fi
}

# Fast-forward this checkout from its upstream, then run the installer again.
# A dirty, detached, or diverged tree is left as it is. Same rule as
# omarchy-dev-sync: never stash, reset, or merge local work.
omargb_update_checkout() {
  local checkout=$1 relaunch=$2
  shift 2
  local toplevel branch remote merge_ref current target
  [[ ${OMARGB_INSTALL_UPDATE:-1} == 1 ]] || return 0
  [[ -z ${OMARGB_INSTALL_UPDATED:-} ]] || return 0
  toplevel=$(git -C "$checkout" rev-parse --show-toplevel 2>/dev/null) || return 0
  [[ $(readlink -f "$checkout") == $(readlink -f "$toplevel") ]] || return 0
  branch=$(git -C "$toplevel" symbolic-ref --quiet --short HEAD) || {
    omargb_warn "Warning: repo update skipped (detached HEAD)."
    return 0
  }
  remote=$(git -C "$toplevel" config --get "branch.$branch.remote" 2>/dev/null || true)
  merge_ref=$(git -C "$toplevel" config --get "branch.$branch.merge" 2>/dev/null || true)
  if [[ -z $remote || $remote == "." || $merge_ref != refs/heads/* ]]; then
    omargb_warn "Warning: repo update skipped (no remote tracking branch)."
    return 0
  fi
  if [[ -n $(git -C "$toplevel" status --porcelain) ]]; then
    omargb_warn "Warning: repo update skipped (this checkout has local changes)."
    return 0
  fi
  omargb_muted "Checking this checkout for updates ($remote/${merge_ref#refs/heads/})..."
  if ! GIT_TERMINAL_PROMPT=0 git -C "$toplevel" fetch --quiet "$remote" "$merge_ref"; then
    omargb_warn "Warning: repo update fetch failed; continuing with this checkout."
    return 0
  fi
  current=$(git -C "$toplevel" rev-parse HEAD)
  target=$(git -C "$toplevel" rev-parse FETCH_HEAD)
  [[ $current != "$target" ]] || return 0
  if ! git -C "$toplevel" merge-base --is-ancestor "$current" "$target"; then
    omargb_warn "Warning: repo update skipped (local history is ahead or diverged)."
    return 0
  fi
  if [[ -n $(git -C "$toplevel" status --porcelain) ]]; then
    omargb_warn "Warning: repo update skipped (checkout changed during fetch)."
    return 0
  fi
  if ! git -C "$toplevel" merge --ff-only "$target"; then
    printf '%s\n' "Warning: repo update failed; stopping." >&2
    return 1
  fi
  omargb_ok "Updated this checkout to ${target:0:7}."
  export OMARGB_INSTALL_UPDATED=1
  exec bash "$relaunch" "$@"
}

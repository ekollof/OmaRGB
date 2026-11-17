#!/bin/bash
# Omarchy calls this after a theme change. The theme name in $1 is not used:
# the active colors.toml is the colour source.
set -euo pipefail
# The palette watcher starts its own apply when the theme directory is
# replaced. Skip this one when that apply already painted the same palette.
exec "$HOME/.local/bin/omargb" apply --debounce

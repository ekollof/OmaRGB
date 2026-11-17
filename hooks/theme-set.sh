#!/bin/bash
# Omarchy calls this after a theme change. The theme name in $1 is not used:
# the active colors.toml is the colour source.
set -euo pipefail
exec "$HOME/.local/bin/omargb" apply

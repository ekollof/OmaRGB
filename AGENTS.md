# AGENTS.md

OmaRGB paints RGB hardware from the active Omarchy theme. This file is the working agreement for that tree. The user-facing overview is [README.md](README.md). Contribution goes through GitHub issues, described in [CONTRIBUTE.md](CONTRIBUTE.md).

## Source of truth

- Colours come only from `~/.local/state/omarchy/current/theme/colors.toml`. `keyboard.rgb` is a one-colour fallback for themes that have no `color0`–`color15`.
- Do not sample wallpaper pixels. Do not invent hues that are not in the theme file.
- A backlight emits every channel. Pastel hexes look coloured on a dark terminal and white as light. `omargb/theme.py` drops the white floor and scales the strongest remaining channel to 255. Keep that. Do not mix colours toward white the way `omarchy-theme-set-openrgb` does.
- Skip terminal chrome `color0`, `color7`, `color8`, and `color15`, and any slot whose chroma peak is under 24.

## What to edit

| Change | Where |
|---|---|
| A known device, existing engine | `share/devices.toml` |
| How a protocol paints | `omargb/engines/<name>.py`, then register it in `omargb/engines/__init__.py` |
| Packages, a system service, or a udev rule a painter needs | `share/painters.toml` |
| Which ids match which engine | `omargb/catalog.py` |
| USB, PCI, board, and Home Assistant discovery | `omargb/scan.py` |
| Install, hooks, login PATH | `install.sh`, `uninstall.sh`, `hooks/`, `shims/`, `systemd/` |
| Bar icon and painting controls | `shell/`, read by `omargb` from `~/.config/omargb/behaviour.json` |
| Wiki notes (devices, engines, extending, from Omarchy) | `docs/wiki/` and the GitHub wiki, which is the separate repo `https://github.com/ekollof/OmaRGB.wiki.git` |

The site pages under `docs/wiki/` and the GitHub wiki (`Home`, `Devices`, `Engines`, `Extending`, `From-Omarchy`, and `_Sidebar`) say the same thing. A change to either is unfinished until the other matches.

Paint a device only when the database matches it. An OpenRGB keyboard with a per-LED mode and more than one LED is the exception: the server reports the type, and no row is required. An unlisted lamp stays dark.

## Engines

An engine is a class with `name` and `apply(theme, targets, dry_run) -> str | None`. `dry_run` must not open hardware. A failure string that contains `unavailable`, `rejected`, `missing`, `failed`, or `not ready` lets `omargb/apply.py` try `fallback` from the database row.

- `vanguard_k08` reads the live 8192-byte map and writes only the primary RGB bytes at `0x09 + led*50 + 2`. Leave the macro table at `0x1960` alone. Do not commit a personal `block-template.bin`. The firmware needs about 350 ms between the four chunks.
- `openrgb` talks to the local server on `127.0.0.1:6742` (protocol 4). A keyboard the server reports, with a per-LED mode and more than one LED, gets the theme stops left to right, one colour per column. It does not need a database row. Anything else with a per-LED mode and more than one LED gets the theme stops only when a row names it. A listed device with no per-LED gradient gets one theme colour, at that mode's full brightness. It does not own devices another engine already claimed.
- `openlinkhub` posts to `http://127.0.0.1:27003/api/color/all`. The `openlinkhub` binary itself panics outside the system service.
- `asus_rog` and `framework16` replace Omarchy quattro's laptop painters (`omarchy-theme-set-keyboard-asus-rog` and `omarchy-theme-set-keyboard-f16`). The database rows match the same machines as `omarchy-hw-asus-rog` and `omarchy-hw-framework16`. Framework hue and saturation follow `colorsys`, which is what Omarchy's QMK helper matches. The colour is still the theme solid from `colors.toml`, not the raw `keyboard.rgb` accent.
- `homeassistant` reads `~/.config/hass.cfg` (`[auth]` with `server`, `token`, and `lamp`), the same file wallpaperctl uses. It sets `rgb_color` on a lamp that is already on. The colour is one theme stop chosen by `behaviour.json` `strategy` (`warmest` by default, also `least_blue`, `most_saturated`, `coolest`, `brightest`), scored the way wallpaperctl's `rgb_color_strategy` scores a palette line. Other engines keep the most saturated stop. The file must not be readable by group or other. `dry_run` does not call the API. A lamp stays dark unless that file lists it and a database row matches the entity id. Do not commit the config or the token.

## Omarchy boundaries

- Do not edit `/usr/share/omarchy` or the Omarchy source checkout to add a device. This project overrides those painters with hooks and PATH shims.
- `install.sh` is allowed to step aside `~/.config/omarchy/hooks/*/vanguard-k08-rgb` and disable `vanguard-k08-theme-watch.service`. `uninstall.sh` puts them back from `~/.local/state/omargb/install.json`. A later install fast-forwards this checkout from its upstream when the worktree is clean, then refreshes the hooks, shims, units, and login PATH file and drops copies the tree no longer ships. It does not stash, reset, or merge local work, and it does not restore those painters. The `omargb` link points at this checkout, so the device database follows the tree.
- Shims live in `~/.local/share/omargb/shims` and are prepended from `~/.config/uwsm/env.d/90-omargb` at the next graphical login. The theme-set hook is what paints before that login.
- Do not open an Omarchy pull request for this work.

## Checks

```bash
python3 tests/test_omargb.py
omargb plan
```

`plan` must not write to hardware. Run `omargb apply` only when the user wants the lights changed. The keyboard write takes a couple of seconds. Hold `~/.local/state/omargb/apply.lock` for the whole apply, which `omargb/cli.py` already does.

## Style

- Python 3.11 or newer. Standard library only.
- Bash scripts use `#!/bin/bash`, `set -euo pipefail`, `[[ ]]`, and `(( ))`.
- Markdown lines are not hard-wrapped.
- Device ids in the database are lowercase hex `vendor:product`, or a shell wildcard for DMI, OpenRGB, and Home Assistant entity names.
- One coherent change per commit. Do not commit or push unless the user asks.

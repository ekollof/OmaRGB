# Contributing

Work starts as a GitHub issue on this repository. Open the issue before changing code. A pull request that has no issue is sent back to one.

Search the open issues first. If yours is already there, add the missing hardware details to it instead of opening a second one.

## 1. Open an issue

Use one of these titles:

- `device: <product name>` for hardware the database does not paint yet
- `engine: <name>` for a protocol that no current engine speaks
- `bug: <what the lights did>` for a match that paints the wrong colour, misses the device, or breaks a key map

The issue body needs the identifiers the database matches on, and nothing secret:

- `lsusb` line for the device, including the `vendor:product` id
- `lspci -nn` line when the light is on PCI
- `cat /sys/class/dmi/id/board_vendor` and `board_name` when it is a laptop or motherboard backlight
- `omargb plan` output
- `openrgb --list-devices` when OpenRGB can see it
- What the theme colour was, and what the hardware actually showed

A photo of the device helps. Do not paste macro dumps, keyboard maps, or a lighting template binary. Those are personal to the machine that captured them.

A new device that an existing engine can already paint only needs a `share/devices.toml` row. Say which engine and whether the effect should be `solid` or `gradient`.

## 2. Wait for the issue

A maintainer labels it:

- `ready` means the approach is agreed and a pull request can start
- `needs-info` means the identifiers above are still missing
- `wont-paint` means the device stays dark on purpose

Do not open the pull request on `needs-info` or `wont-paint`.

## 3. Send the pull request

Branch from the default branch. Mention the issue in the pull request body (`Fixes #123`). Keep the change to that issue.

- Database-only changes touch `share/devices.toml` and, when the match rule is new, a case in `tests/test_omargb.py`.
- A new engine is a module in `omargb/engines/`, registered in `omargb/engines/__init__.py`, with `apply(theme, targets, dry_run)`. `dry_run` must not open the device.
- Colours still come from `colors.toml` through `omargb/theme.py`. Do not add a second palette.
- Run `python3 tests/test_omargb.py` and paste the result in the pull request.
- If you can run the hardware, also paste `omargb plan` from after the change.

`assets/omarchy-logo.svg` is the Omarchy logo from [omarchy.org/brand/omarchy-logo.svg](https://omarchy.org/brand/omarchy-logo.svg). Leave that file as published. `assets/logo.jpg` is the project lockup made from that mark. Do not replace either with a newly drawn symbol.

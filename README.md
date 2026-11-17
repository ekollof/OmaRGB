# OmaRGB

<p>
  <img src="assets/logo.jpg" alt="OmaRGB" width="192">
</p>

OmaRGB paints RGB hardware from the active Omarchy theme. The mark is the [Omarchy logo](https://omarchy.org/brand/omarchy-logo.svg), kept as published in `assets/omarchy-logo.svg`, with the project name added in `assets/logo.jpg`. `colors.toml` is the only colour source. Mice, DRAM, motherboard lighting, Corsair hubs, laptop keyboards, and the Sound BlasterX Vanguard K08 are selected from a database of USB, PCI, and board ids, then handed to a matching engine.

Omarchy's own painters (`omarchy-theme-set-keyboard`, OpenRGB, ASUS `asusctl`, Framework `qmk_hid`) turn the theme accent into a pale colour and send that. After install, those commands are shadowed and the theme-set hook runs OmaRGB instead.

## Install

```bash
~/Work/OmaRGB/install.sh
```

This links `omargb` onto `PATH`, installs a theme-set hook and a login hook, and watches `~/.local/state/omarchy/current/theme` so a wallpaper palette update still recolours the hardware. wallpaperctl rewrites `colors.toml` without running `omarchy theme set`.

The next graphical login puts `~/.local/share/omargb/shims` first on `PATH`, which makes the stock RGB commands do nothing. Until that login, Omarchy may paint first and the theme hook corrects it.

`uninstall.sh` removes the hooks, the watcher, and the shims, and puts back anything the installer stepped aside.

## Commands

```bash
omargb plan     # show the match and the colours, change nothing
omargb apply    # paint matched hardware
```

A backlight cannot show a pastel. Each chosen theme hue has its white floor removed and its strongest channel turned fully on. Gradient devices get those stops in hue order. One-colour devices get the strongest stop. Black, white, and the terminal chrome slots `color0`, `color7`, `color8`, and `color15` are skipped.

## Adding hardware

New devices and engines start as a GitHub issue. The steps are in [CONTRIBUTE.md](CONTRIBUTE.md). The entry itself is one `[[device]]` block in `share/devices.toml`:

| Field | Meaning |
|---|---|
| `bus` | `usb`, `pci`, `dmi`, or `openrgb` |
| `id` | `vendor:product` hex, `vendor:name` for a DMI board, product family, or product name (wildcards allowed), or an OpenRGB device name |
| `engine` | `vanguard_k08`, `openrgb`, `openlinkhub`, `asus_rog`, or `framework16` |
| `effect` | `solid` or `gradient` |
| `openrgb` | Name substring, when that engine has to find the device inside OpenRGB |
| `fallback` | Engine used when the first one cannot run |

USB and PCI ids come from `lsusb` and `lspci -nn`. A board that has no USB lighting id is matched on `board_vendor:board_name`, `sys_vendor:product_family`, or `sys_vendor:product_name` from `/sys/class/dmi/id`. The ASUS ROG and Framework Laptop 16 rows use the same DMI checks as Omarchy's `omarchy-hw-asus-rog` and `omarchy-hw-framework16`. DRAM that only OpenRGB can see uses `bus = "openrgb"`. Anything not listed is left alone.

Engines live in `omargb/engines/`. A new engine is a class with `name` and `apply(theme, targets, dry_run)`, registered in `omargb/engines/__init__.py`.

## Engines shipped here

- `vanguard_k08` speaks the K08 hidraw protocol and changes only LED colours, so the key map is left as the keyboard has it.
- `openrgb` sets static mode at full brightness to the theme colour. It does not mix the colour toward white.
- `openlinkhub` posts the theme colour to the local OpenLinkHub service (`127.0.0.1:27003`, `/api/color/all`). If that service is down, the Commander Pro entry falls back to OpenRGB.
- `asus_rog` and `framework16` cover the laptop keyboards Omarchy used to paint itself.

## Tests

```bash
python3 tests/test_omargb.py
```

Agents working in this tree should read [AGENTS.md](AGENTS.md) first.

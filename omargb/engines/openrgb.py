"""Devices OpenRGB already drives: mice, DRAM, motherboard lighting."""

import shutil
import subprocess

from omargb.catalog import Target
from omargb.theme import Theme


class OpenRgb:
    name = "openrgb"

    def apply(self, theme: Theme, targets: list[Target], dry_run: bool) -> str:
        devices: list[tuple[int, str]] = []
        for target in targets:
            colour = _colour(theme, target.entry.effect)
            for index, device_name in target.openrgb_devices:
                devices.append((index, f"{index}:{device_name} {colour}"))
        if not devices:
            return "openrgb: nothing addressed"
        if dry_run:
            return "openrgb dry-run " + ", ".join(note for _index, note in devices)
        if shutil.which("openrgb") is None:
            return "openrgb: command missing"
        command = ["openrgb"]
        colour_for = {}
        for target in targets:
            colour_for_target = _colour(theme, target.entry.effect).removeprefix("#")
            for index, _name in target.openrgb_devices:
                colour_for[index] = colour_for_target
        for index, colour in colour_for.items():
            command.extend(["-d", str(index), "-m", "static", "-c", colour, "-b", "100"])
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            tail = detail[-1] if detail else f"exit {result.returncode}"
            return f"openrgb: {tail}"
        return "openrgb " + ", ".join(note for _index, note in devices)


def list_devices() -> list[tuple[int, str]]:
    if shutil.which("openrgb") is None:
        return []
    result = subprocess.run(
        ["openrgb", "--list-devices"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    devices = []
    for line in result.stdout.splitlines():
        if not line[:1].isdigit() or ":" not in line:
            continue
        index, name = line.split(":", 1)
        devices.append((int(index), name.strip()))
    return devices


def _colour(theme: Theme, effect: str) -> str:
    if effect == "gradient" and theme.stops:
        return theme.stop_hexes()[0]
    return theme.solid_hex()

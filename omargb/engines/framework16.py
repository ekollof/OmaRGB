"""Framework Laptop 16 keyboard via qmk_hid. Replaces omarchy-theme-set-keyboard-f16.

Hue and saturation follow colorsys, which is what Omarchy's QMK helper matches.
"""

import colorsys
import shutil
import subprocess

from omargb.catalog import Target
from omargb.theme import Theme


class Framework16:
    name = "framework16"

    def apply(self, theme: Theme, targets: list[Target], dry_run: bool) -> str | None:
        if not targets:
            return None
        hue, saturation = qmk_hue_saturation(theme.solid)
        if dry_run:
            return f"framework16 dry-run hue {hue} saturation {saturation}"
        if shutil.which("qmk_hid") is None:
            return "framework16: qmk_hid missing"
        calls = (
            ["qmk_hid", "via", "--rgb-effect", "1"],
            ["qmk_hid", "via", "--rgb-hue", str(hue)],
            ["qmk_hid", "via", "--rgb-saturation", str(saturation)],
            ["qmk_hid", "via", "--rgb-brightness", "100"],
            ["qmk_hid", "via", "--save"],
        )
        for command in calls:
            result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
            if result.returncode != 0:
                return "framework16: qmk_hid failed"
        return f"framework16 hue {hue} saturation {saturation}"


def qmk_hue_saturation(rgb: tuple[int, int, int]) -> tuple[int, int]:
    hue, saturation, _value = colorsys.rgb_to_hsv(*(channel / 255 for channel in rgb))
    return int(hue * 255), int(saturation * 255)

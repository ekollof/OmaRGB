"""ASUS ROG laptop keyboards via asusctl. Replaces omarchy-theme-set-keyboard-asus-rog."""

import shutil
import subprocess

from omargb.catalog import Target
from omargb.theme import Theme


class AsusRog:
    name = "asus_rog"

    def apply(self, theme: Theme, targets: list[Target], dry_run: bool) -> str | None:
        if not targets:
            return None
        colour = theme.solid_hex().removeprefix("#")
        if dry_run:
            return f"asus_rog dry-run {colour}"
        if shutil.which("asusctl") is None:
            return "asus_rog: asusctl missing"
        result = subprocess.run(
            ["asusctl", "aura", "effect", "static", "-c", colour],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            return "asus_rog: asusctl failed"
        return f"asus_rog {colour}"

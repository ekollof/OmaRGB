"""Omarchy presentation for the omargb command.

A terminal gets the theme border from gum and the green or red mark from
omarchy-show-done. Hooks and the theme watcher are not a terminal, so they
keep the plain report.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from omargb.apply import Report, _failed

_GUM_ENV = re.compile(r'hl\.env\("([A-Z0-9_]+)", "([^"]*)"\)')


def show_report(report: Report, command: str) -> None:
    lines = report.lines or ["nothing to report"]
    if not sys.stdout.isatty() or shutil.which("gum") is None:
        print("\n".join(lines))
        return
    _load_gum_env()
    title = "OmaRGB plan" if command == "plan" else "OmaRGB"
    subprocess.run(
        ["gum", "style", "--border", "normal", "--padding", "1 2", "--", title, "", *(f"• {line}" for line in lines)],
        check=False,
    )
    color, label = status_mark(report, command)
    print(f"\033[{color}m● \033[0m{label}")


def status_mark(report: Report, command: str) -> tuple[str, str]:
    if report.not_ready:
        return "31", "Not ready"
    if any(_failed(line) for line in report.lines):
        return "31", "Failed"
    if _quiet(report):
        return "90", "Nothing to paint"
    if command == "plan":
        return "32", "Ready"
    return "32", "Done"


def _quiet(report: Report) -> bool:
    if not report.lines:
        return True
    opening = report.lines[0]
    return opening.startswith("no theme") or "matches no RGB" in opening


def _load_gum_env() -> None:
    path = Path.home() / ".local/state/omarchy/current/theme/gum_env.lua"
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        match = _GUM_ENV.search(line)
        if match:
            os.environ[match.group(1)] = match.group(2)

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
    columns = shutil.get_terminal_size(fallback=(80, 24)).columns
    width = max(42, min(64, columns))
    title = "OmaRGB plan" if command == "plan" else "OmaRGB"
    body = [title, "", *present_lines(lines, width - 6)]
    subprocess.run(
        ["gum", "style", "--border", "normal", "--padding", "1 2", "--width", str(width), "--", *body],
        check=False,
    )
    color, label = status_mark(report, command)
    print(f"\033[{color}m● \033[0m{label}")


def present_lines(lines: list[str], inner: int) -> list[str]:
    """Short rows for the gum card. inner is the text width inside the padding."""
    rows: list[str] = []
    for line in lines:
        if rows:
            rows.append("")
        rows.extend(_present_line(line, max(inner, 16)))
    return rows


def _present_line(line: str, inner: int) -> list[str]:
    theme = re.fullmatch(r"theme solid (#(?:[0-9a-fA-F]{6})) stops (.+)", line)
    if theme:
        return _theme(theme.group(1), theme.group(2).split(), inner)
    if line.startswith(("vanguard_k08 ", "vanguard_k08 dry-run ")):
        return ["vanguard_k08", "  gradient"]
    devices = _openrgb_devices(line)
    if devices is not None:
        return _section("openrgb", devices, inner)
    named = _openlinkhub_names(line)
    if named is not None:
        return _section("openlinkhub", named, inner)
    lamps = _homeassistant_names(line)
    if lamps is not None:
        return _section("homeassistant", lamps, inner)
    return _wrap(line, inner)


def _theme(solid: str, stops: list[str], inner: int) -> list[str]:
    return [f"solid  {solid}", *_flow("stops  ", stops, inner)]


def _flow(prefix: str, words: list[str], inner: int) -> list[str]:
    rows: list[str] = []
    current = prefix
    indent = " " * len(prefix)
    for word in words:
        piece = word if current in (prefix, indent) else f" {word}"
        if len(current) + len(piece) > inner and current not in (prefix, indent):
            rows.append(current.rstrip())
            current = indent + word
        else:
            current += piece
    if current not in (prefix, indent):
        rows.append(current.rstrip())
    return rows


def _section(title: str, items: list[str], inner: int) -> list[str]:
    rows = [title]
    for item in _group(items):
        rows.extend(f"  {part}" for part in _wrap(item, max(8, inner - 2)))
    return rows


def _group(names: list[str]) -> list[str]:
    order: list[str] = []
    counts: dict[str, int] = {}
    for name in names:
        if name not in counts:
            order.append(name)
            counts[name] = 0
        counts[name] += 1
    return [name if counts[name] == 1 else f"{name} ×{counts[name]}" for name in order]


def _openrgb_devices(line: str) -> list[str] | None:
    if line.startswith("openrgb dry-run "):
        body = line.removeprefix("openrgb dry-run ")
    elif line.startswith("openrgb ") and not line.startswith("openrgb:"):
        body = line.removeprefix("openrgb ")
    else:
        return None
    names = []
    for note in body.split(", "):
        match = re.fullmatch(r"(?:\d+:)?(.+) (#[0-9a-fA-F]{6})", note.strip())
        names.append(match.group(1) if match else note.strip())
    return names


def _homeassistant_names(line: str) -> list[str] | None:
    if line.startswith("homeassistant dry-run "):
        body = line.removeprefix("homeassistant dry-run ")
    elif line.startswith("homeassistant ") and not line.startswith("homeassistant:"):
        body = line.removeprefix("homeassistant ")
    else:
        return None
    names = []
    for note in body.split(", "):
        match = re.fullmatch(r"(.+) (#[0-9a-fA-F]{6})", note.strip())
        names.append(match.group(1) if match else note.strip())
    return names


def _openlinkhub_names(line: str) -> list[str] | None:
    if not line.startswith("openlinkhub ") or _failed(line):
        return None
    body = line.removeprefix("openlinkhub dry-run ").removeprefix("openlinkhub ")
    match = re.fullmatch(r"(.+) (#[0-9a-fA-F]{6})", body)
    text = match.group(1) if match else body
    return [name.strip() for name in text.split(",") if name.strip()]


def _wrap(line: str, inner: int) -> list[str]:
    words = line.split()
    if not words:
        return [""]
    rows: list[str] = []
    current = words[0]
    for word in words[1:]:
        if len(current) + 1 + len(word) > inner:
            rows.append(current)
            current = word
        else:
            current = f"{current} {word}"
    rows.append(current)
    return rows


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

"""Plan and paint every database match from the active theme."""

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from omargb.catalog import Target, load_database, match
from omargb.engines import ENGINES
from omargb.engines.openrgb import list_devices
from omargb.scan import scan
from omargb.theme import Theme, default_colors_path, load_theme


@dataclass
class Report:
    lines: list[str]
    not_ready: bool = False

    def text(self) -> str:
        return "\n".join(self.lines)


def run(
    colors: Path | None = None,
    database: Path | None = None,
    dry_run: bool = False,
    root: Path | None = None,
    openrgb_devices: list[tuple[int, str]] | None = None,
) -> Report:
    theme = load_theme(colors or default_colors_path())
    if theme is None:
        return Report(["no theme colours to apply"])
    entries = load_database(database)
    hardware = scan(root)
    needs_openrgb = any(
        entry.bus == "openrgb" or "openrgb" in (entry.engine, entry.fallback) for entry in entries
    )
    if openrgb_devices is None and needs_openrgb:
        openrgb_devices = list_devices()
    targets = match(entries, hardware, openrgb_devices or [])
    return _apply(theme, targets, dry_run)


def _apply(theme: Theme, targets: list[Target], dry_run: bool) -> Report:
    if not targets:
        return Report([f"theme {theme.solid_hex()} matches no RGB devices"])
    grouped: dict[str, list[Target]] = defaultdict(list)
    for target in targets:
        grouped[target.entry.engine].append(target)
    lines = [f"theme solid {theme.solid_hex()} stops {' '.join(theme.stop_hexes())}"]
    not_ready = False
    for name, group in grouped.items():
        engine = ENGINES.get(name)
        if engine is None:
            lines.append(f"{name}: unknown engine")
            continue
        outcome = engine.apply(theme, group, dry_run)
        if not outcome:
            continue
        lines.append(outcome)
        if "not ready" in outcome:
            not_ready = True
        if _failed(outcome) and group[0].entry.fallback:
            fallback = ENGINES.get(group[0].entry.fallback)
            if fallback is not None:
                lines.append(fallback.apply(theme, group, dry_run) or f"{group[0].entry.fallback}: nothing to do")
    return Report(lines, not_ready)


def _failed(outcome: str) -> bool:
    return any(word in outcome for word in ("unavailable", "rejected", "missing", "failed", "not ready"))

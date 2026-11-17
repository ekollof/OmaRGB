"""Painter packages for the hardware actually present.

install.sh prints this report and installs only those packages.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from omargb.catalog import ROOT, load_database, match
from omargb.scan import Hardware

PAINTERS = ROOT / "share" / "painters.toml"


@dataclass(frozen=True)
class Painter:
    engine: str
    source: str
    packages: tuple[str, ...]
    service: str
    udev: str
    udev_dest: str


def load_painters(path: Path | None = None) -> dict[str, Painter]:
    path = path or PAINTERS
    data = tomllib.loads(path.read_text())
    painters = {}
    for row in data.get("painter", []):
        source = row.get("source") or "arch"
        if source not in ("arch", "aur"):
            raise ValueError(f"{row.get('engine')}: source must be arch or aur")
        painters[row["engine"]] = Painter(
            engine=row["engine"],
            source=source,
            packages=tuple(row.get("packages") or ()),
            service=row.get("service") or "",
            udev=row.get("udev") or "",
            udev_dest=row.get("udev_dest") or "",
        )
    return painters


def report(hardware: list[Hardware], openrgb_devices: list[tuple[int, str]] | None = None) -> str:
    """Tab-separated lines: device, package, service, udev."""
    entries = load_database()
    painters = load_painters()
    names: list[str] = []
    engines: list[str] = []
    for target in match(entries, hardware, openrgb_devices or []):
        label = target.hardware.name or target.entry.name
        if label not in names:
            names.append(label)
        for engine in (target.entry.engine, target.entry.fallback):
            if engine and engine not in engines:
                engines.append(engine)
    lines = [f"device\t{name}" for name in names]
    seen: set[tuple[str, str]] = set()
    services: list[str] = []
    rules: list[tuple[str, str]] = []
    for engine in engines:
        painter = painters.get(engine)
        if painter is None:
            continue
        for package in painter.packages:
            key = (painter.source, package)
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"package\t{painter.source}\t{package}")
        if painter.service and painter.service not in services:
            services.append(painter.service)
            lines.append(f"service\t{painter.service}")
        if painter.udev and painter.udev_dest and (painter.udev, painter.udev_dest) not in rules:
            rules.append((painter.udev, painter.udev_dest))
            lines.append(f"udev\t{painter.udev}\t{painter.udev_dest}")
    return "\n".join(lines) + ("\n" if lines else "")

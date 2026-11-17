"""Match scanned hardware against the device database."""

import fnmatch
import tomllib
from dataclasses import dataclass
from pathlib import Path

from omargb.scan import Hardware

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE = ROOT / "share" / "devices.toml"


@dataclass(frozen=True)
class Entry:
    bus: str
    ident: str
    name: str
    engine: str
    effect: str
    openrgb: str
    fallback: str


@dataclass(frozen=True)
class Target:
    entry: Entry
    hardware: Hardware
    openrgb_devices: tuple[tuple[int, str], ...] = ()


def load_database(path: Path | None = None) -> list[Entry]:
    path = path or DEFAULT_DATABASE
    data = tomllib.loads(path.read_text())
    entries = []
    for row in data.get("device", []):
        entries.append(
            Entry(
                bus=row["bus"],
                ident=row["id"],
                name=row.get("name") or row["id"],
                engine=row["engine"],
                effect=row.get("effect") or "solid",
                openrgb=row.get("openrgb") or "",
                fallback=row.get("fallback") or "",
            )
        )
    return entries


def match(entries: list[Entry], hardware: list[Hardware], openrgb_devices: list[tuple[int, str]] | None = None) -> list[Target]:
    """Pair database rows with hardware.

    openrgb_devices is the indexed list from `openrgb --list-devices`. A row
    with bus "openrgb" matches those names. Other rows match USB, PCI, or DMI,
    and take the OpenRGB indices whose names contain `openrgb` when that engine
    needs them.
    """
    openrgb_devices = openrgb_devices or []
    claimed: set[int] = set()
    claimed_hass: set[str] = set()
    targets: list[Target] = []

    for entry in entries:
        if entry.bus == "openrgb":
            hits = _unclaimed(openrgb_devices, claimed, lambda name: fnmatch.fnmatchcase(name, entry.ident))
            if not hits:
                continue
            claimed.update(index for index, _name in hits)
            targets.append(Target(entry, Hardware("openrgb", entry.ident, entry.name), tuple(hits)))
            continue

        if entry.bus == "hass":
            hits = [item for item in hardware if _ident_matches(entry, item) and item.ident not in claimed_hass]
            claimed_hass.update(item.ident for item in hits)
            targets.extend(Target(entry, item) for item in hits)
            continue

        device = next((item for item in hardware if _ident_matches(entry, item)), None)
        if device is None:
            continue
        indices: tuple[tuple[int, str], ...] = ()
        if entry.openrgb and (entry.engine == "openrgb" or entry.fallback == "openrgb"):
            needle = entry.openrgb.lower()
            hits = _unclaimed(openrgb_devices, claimed, lambda name, needle=needle: needle in name.lower())
            if entry.engine == "openrgb" and not hits:
                continue
            claimed.update(index for index, _name in hits)
            indices = tuple(hits)
        targets.append(Target(entry, device, indices))
    return targets


def _ident_matches(entry: Entry, item: Hardware) -> bool:
    if item.bus != entry.bus:
        return False
    # DMI strings vary in case. Omarchy's Framework check is case-insensitive.
    if item.bus == "dmi":
        return fnmatch.fnmatchcase(item.ident.casefold(), entry.ident.casefold())
    return fnmatch.fnmatchcase(item.ident, entry.ident)


def _unclaimed(devices, claimed, predicate):
    return [
        (index, name)
        for index, name in devices
        if index not in claimed and predicate(name)
    ]

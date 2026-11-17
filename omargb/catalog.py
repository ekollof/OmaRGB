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
    # OpenRGB index and LED count for devices that can take one colour per LED.
    openrgb_leds: tuple[tuple[int, int], ...] = ()


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

    openrgb_devices is the indexed list from the OpenRGB server. A row with
    bus "openrgb" matches those names. Other rows match USB, PCI, or DMI, and
    take the OpenRGB indices whose names contain `openrgb` when that engine
    needs them. A third field, when present, is the per-LED count. A fourth
    field marks an OpenRGB keyboard. Any keyboard with more than one LED that
    no row claimed is painted too, so a new keyboard does not need its own row.
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
            claimed.update(index for index, _name, _leds in hits)
            targets.append(Target(entry, Hardware("openrgb", entry.ident, entry.name), _names(hits), _leds(hits)))
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
        leds: tuple[tuple[int, int], ...] = ()
        if entry.openrgb and (entry.engine == "openrgb" or entry.fallback == "openrgb"):
            needle = entry.openrgb.lower()
            hits = _unclaimed(openrgb_devices, claimed, lambda name, needle=needle: needle in name.lower())
            if entry.engine == "openrgb" and not hits:
                continue
            claimed.update(index for index, _name, _count in hits)
            indices = _names(hits)
            leds = _leds(hits)
        targets.append(Target(entry, device, indices, leds))
    targets.extend(_openrgb_keyboards(openrgb_devices, claimed))
    return targets


def _ident_matches(entry: Entry, item: Hardware) -> bool:
    if item.bus != entry.bus:
        return False
    # DMI strings vary in case. Omarchy's Framework check is case-insensitive.
    if item.bus == "dmi":
        return fnmatch.fnmatchcase(item.ident.casefold(), entry.ident.casefold())
    return fnmatch.fnmatchcase(item.ident, entry.ident)


def _openrgb_keyboards(devices, claimed: set[int]) -> list[Target]:
    """Keyboards the server reported, other than ones a database row already claimed."""
    found = []
    for device in devices:
        index, name, *rest = device
        leds = int(rest[0]) if rest else 0
        keyboard = bool(rest[1]) if len(rest) > 1 else False
        if index in claimed or not keyboard or leds < 2 or not name:
            continue
        claimed.add(index)
        entry = Entry("openrgb", name, name, "openrgb", "gradient", "", "")
        found.append(Target(entry, Hardware("openrgb", name, name), ((index, name),), ((index, leds),)))
    return found


def _unclaimed(devices, claimed, predicate):
    found = []
    for device in devices:
        index, name, *rest = device
        leds = int(rest[0]) if rest else 0
        if index not in claimed and predicate(name):
            found.append((int(index), name, leds))
    return found


def _names(hits) -> tuple[tuple[int, str], ...]:
    return tuple((index, name) for index, name, _leds in hits)


def _leds(hits) -> tuple[tuple[int, int], ...]:
    return tuple((index, count) for index, _name, count in hits if count > 1)

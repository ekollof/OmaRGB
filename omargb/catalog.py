"""Match scanned hardware against the device database."""

import fnmatch
import tomllib
from dataclasses import dataclass
from pathlib import Path

from omargb.scan import Hardware

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE = ROOT / "share" / "devices.toml"
DEFAULT_OPENLINKHUB = ROOT / "share" / "openlinkhub.toml"


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
    field marks an OpenRGB keyboard. A fifth field marks a device that can
    take a colour at all. Any such device that no row claimed is painted too.

    USB ids in share/openlinkhub.toml use OpenLinkHub, unless that controller
    can take a colour per LED. A database row for the same USB id wins.
    """
    openrgb_devices = openrgb_devices or []
    claimed: set[int] = set()
    claimed_hass: set[str] = set()
    claimed_usb: set[str] = set()
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
        if device.bus == "usb":
            claimed_usb.add(device.ident.lower())
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
    targets.extend(_openlinkhub_usb(hardware, openrgb_devices, claimed, claimed_usb))
    targets.extend(_openrgb_rest(openrgb_devices, claimed))
    return targets


def _ident_matches(entry: Entry, item: Hardware) -> bool:
    if item.bus != entry.bus:
        return False
    # DMI strings vary in case. Omarchy's Framework check is case-insensitive.
    if item.bus == "dmi":
        return fnmatch.fnmatchcase(item.ident.casefold(), entry.ident.casefold())
    return fnmatch.fnmatchcase(item.ident, entry.ident)


def load_openlinkhub(path: Path | None = None) -> list[tuple[str, str]]:
    """USB id and name from the OpenLinkHub supported-device list."""
    path = path or DEFAULT_OPENLINKHUB
    if not path.is_file():
        return []
    data = tomllib.loads(path.read_text())
    found = []
    for row in data.get("device", []):
        found.append((str(row["id"]).lower(), row.get("name") or row["id"]))
    return found


def _openlinkhub_usb(hardware, devices, claimed: set[int], claimed_usb: set[str]) -> list[Target]:
    """Hubs and other OpenLinkHub USB devices that no database row claimed.

    A controller that can take a colour on each LED stays with OpenRGB.
    """
    by_id = {ident: name for ident, name in load_openlinkhub()}
    found = []
    for item in hardware:
        if item.bus != "usb":
            continue
        ident = item.ident.lower()
        if ident in claimed_usb or ident not in by_id:
            continue
        label = by_id[ident]
        related = _related(devices, claimed, (item.name, label))
        if any(leds > 1 for _index, _name, leds, _keyboard in related):
            continue
        claimed_usb.add(ident)
        claimed.update(index for index, _name, _leds, _keyboard in related)
        fallback = "openrgb" if related else ""
        hits = [(index, name, leds) for index, name, leds, _keyboard in related]
        entry = Entry("usb", ident, label, "openlinkhub", "solid", "", fallback)
        found.append(Target(entry, Hardware("usb", ident, item.name or label), _names(hits), _leds(hits)))
    return found


def _openrgb_rest(devices, claimed: set[int]) -> list[Target]:
    """Colourable OpenRGB devices that no row and no OpenLinkHub id claimed.

    More than one per-LED colour is a gradient. A keyboard matrix is still
    painted left to right by the engine. One LED, or a static mode, is one colour.
    """
    found = []
    for device in devices:
        index, name, *rest = device
        leds = int(rest[0]) if rest else 0
        colorable = bool(rest[2]) if len(rest) > 2 else leds > 1
        if index in claimed or not name or not colorable:
            continue
        claimed.add(index)
        effect = "gradient" if leds > 1 else "solid"
        counted = ((index, leds),) if leds > 1 else ()
        entry = Entry("openrgb", name, name, "openrgb", effect, "", "")
        found.append(Target(entry, Hardware("openrgb", name, name), ((index, name),), counted))
    return found


def _related(devices, claimed: set[int], labels: tuple[str, ...]):
    found = []
    for device in devices:
        index, name, *rest = device
        leds = int(rest[0]) if rest else 0
        keyboard = bool(rest[1]) if len(rest) > 1 else False
        if index in claimed or not name:
            continue
        if any(_names_match(label, name) for label in labels if label):
            found.append((int(index), name, leds, keyboard))
    return found


def _names_match(label: str, openrgb_name: str) -> bool:
    """True when the USB product and the OpenRGB name are the same device."""
    left = _core_name(label)
    right = _core_name(openrgb_name)
    if len(left) < 6 or len(right) < 6:
        return False
    return left in right or right in left


def _core_name(name: str) -> str:
    text = "".join(char for char in name.casefold() if char.isalnum())
    if text.startswith("corsair") and len(text) > len("corsair") + 3:
        text = text[len("corsair"):]
    return text


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

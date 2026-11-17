"""Which devices follow the theme.

The bar panel writes this file and `omargb apply` reads it. A missing file
paints every matched device the way the database describes it.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from omargb.catalog import Target
from omargb.theme import STRATEGIES

BUSES = ("usb", "pci", "dmi", "openrgb", "hass")
EFFECTS = ("solid", "gradient")
GRADIENT_ENGINES = {"vanguard_k08"}
MAX_DEVICES = 64
MAX_ID = 200


class BehaviourError(Exception):
    """The behaviour file is present and cannot be trusted."""


@dataclass
class DeviceChoice:
    enabled: bool = True
    effect: str | None = None


@dataclass
class Behaviour:
    enabled: bool = True
    strategy: str = "warmest"
    devices: dict[tuple[str, str], DeviceChoice] = field(default_factory=dict)

    def choice(self, bus: str, ident: str) -> DeviceChoice:
        return self.devices.get((bus, ident), DeviceChoice())

    def set_enabled(self, value: bool) -> None:
        self.enabled = value

    def set_strategy(self, value: str) -> None:
        if value not in STRATEGIES:
            raise BehaviourError("behaviour rejected the strategy")
        self.strategy = value

    def set_device(self, bus: str, ident: str, enabled: bool | None = None, effect: str | None = None) -> None:
        if bus not in BUSES or not _valid_id(ident):
            raise BehaviourError("behaviour rejected the device")
        current = self.choice(bus, ident)
        if enabled is not None:
            current.enabled = enabled
        if effect == "default":
            current.effect = None
        elif effect is not None:
            if effect not in EFFECTS:
                raise BehaviourError("behaviour rejected the effect")
            current.effect = effect
        if current.enabled and current.effect is None:
            self.devices.pop((bus, ident), None)
        else:
            self.devices[(bus, ident)] = current

    def allows(self, bus: str, ident: str) -> bool:
        return self.enabled and self.choice(bus, ident).enabled

    def effect_for(self, bus: str, ident: str, database_effect: str) -> str:
        chosen = self.choice(bus, ident).effect
        return chosen if chosen in EFFECTS else database_effect

    def document(self) -> dict:
        devices = []
        for (bus, ident), choice in sorted(self.devices.items()):
            row = {"bus": bus, "id": ident, "enabled": choice.enabled}
            if choice.effect in EFFECTS:
                row["effect"] = choice.effect
            devices.append(row)
        return {"version": 1, "enabled": self.enabled, "strategy": self.strategy, "devices": devices}


def config_path() -> Path:
    return Path.home() / ".config" / "omargb" / "behaviour.json"


def device_key(target: Target) -> tuple[str, str]:
    """Identity the panel toggles. A lamp is one entity; other rows are one database id."""
    if target.entry.bus == "hass":
        return ("hass", target.hardware.ident)
    return (target.entry.bus, target.entry.ident)


def device_name(target: Target) -> str:
    if target.entry.bus == "hass":
        return target.hardware.ident
    return target.entry.name


def load(path: Path | None = None) -> Behaviour:
    path = path or config_path()
    if not path.is_file():
        return Behaviour()
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise BehaviourError("behaviour rejected the config") from exc
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("enabled"), bool):
        raise BehaviourError("behaviour rejected the config")
    rows = data.get("devices", [])
    if not isinstance(rows, list) or len(rows) > MAX_DEVICES:
        raise BehaviourError("behaviour rejected the config")
    strategy = data.get("strategy", "warmest")
    if strategy not in STRATEGIES:
        raise BehaviourError("behaviour rejected the config")
    behaviour = Behaviour(enabled=data["enabled"], strategy=strategy)
    for row in rows:
        if not isinstance(row, dict):
            raise BehaviourError("behaviour rejected the config")
        bus = row.get("bus")
        ident = row.get("id")
        enabled = row.get("enabled", True)
        effect = row.get("effect")
        if bus not in BUSES or not isinstance(ident, str) or not _valid_id(ident) or not isinstance(enabled, bool):
            raise BehaviourError("behaviour rejected the config")
        if effect is not None and effect not in EFFECTS:
            raise BehaviourError("behaviour rejected the config")
        behaviour.devices[(bus, ident)] = DeviceChoice(enabled=enabled, effect=effect if effect in EFFECTS else None)
    return behaviour


def save(behaviour: Behaviour, path: Path | None = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(behaviour.document(), indent=2) + "\n")
    os.chmod(temporary, 0o644)
    os.replace(temporary, path)


def parse_bool(text: str) -> bool:
    if text == "true":
        return True
    if text == "false":
        return False
    raise BehaviourError("behaviour rejected the value")


def _valid_id(ident: str) -> bool:
    if not ident or len(ident) > MAX_ID or any(ord(char) < 32 for char in ident):
        return False
    return True

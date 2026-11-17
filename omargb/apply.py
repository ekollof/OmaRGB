"""Plan and paint every database match from the active theme."""

from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path

from omargb.behaviour import GRADIENT_ENGINES, Behaviour, BehaviourError, device_key, device_name, load
from omargb.catalog import Target, load_database, match
from omargb.debounce import remember, unchanged
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
    debounce: bool = False,
    state: Path | None = None,
    behaviour: Behaviour | None = None,
    behaviour_path: Path | None = None,
    read_behaviour: bool = False,
) -> Report:
    prepared = prepare(
        colors=colors,
        database=database,
        root=root,
        openrgb_devices=openrgb_devices,
        behaviour=behaviour,
        behaviour_path=behaviour_path,
        read_behaviour=read_behaviour,
    )
    if isinstance(prepared, Report):
        return prepared
    theme, targets, policy = prepared
    if not policy.enabled and not dry_run:
        return Report(["painting is off"])
    active = [_with_effect(target, policy) for target in targets if _device_enabled(target, policy)]
    state = state or Path.home() / ".local/state/omargb"
    if debounce and not dry_run and active and unchanged(state, theme, active):
        return Report([f"unchanged solid {theme.solid_hex()}"])
    report = _apply(theme, targets, dry_run, policy)
    if not dry_run and _settled(report):
        remember(state, theme, active)
    return report


def prepare(
    colors: Path | None = None,
    database: Path | None = None,
    root: Path | None = None,
    openrgb_devices: list[tuple[int, str]] | None = None,
    behaviour: Behaviour | None = None,
    behaviour_path: Path | None = None,
    read_behaviour: bool = False,
) -> Report | tuple[Theme, list[Target], Behaviour]:
    theme = load_theme(colors or default_colors_path())
    if theme is None:
        return Report(["no theme colours to apply"])
    try:
        if behaviour is not None:
            policy = behaviour
        elif read_behaviour or behaviour_path is not None:
            policy = load(behaviour_path)
        else:
            policy = Behaviour()
    except BehaviourError:
        return Report(["behaviour rejected the config"])
    entries = load_database(database)
    hardware = scan(root)
    needs_openrgb = any(
        entry.bus == "openrgb" or "openrgb" in (entry.engine, entry.fallback) for entry in entries
    )
    if openrgb_devices is None and needs_openrgb:
        openrgb_devices = list_devices()
    targets = match(entries, hardware, openrgb_devices or [])
    return theme, targets, policy


def describe(
    colors: Path | None = None,
    database: Path | None = None,
    root: Path | None = None,
    openrgb_devices: list[tuple[int, str]] | None = None,
    behaviour: Behaviour | None = None,
    behaviour_path: Path | None = None,
    read_behaviour: bool = False,
) -> dict:
    """Machine-readable plan for the bar panel. Disabled devices stay in the list."""
    prepared = prepare(
        colors=colors,
        database=database,
        root=root,
        openrgb_devices=openrgb_devices,
        behaviour=behaviour,
        behaviour_path=behaviour_path,
        read_behaviour=read_behaviour,
    )
    if isinstance(prepared, Report):
        return {"ok": False, "error": prepared.text()}
    theme, targets, policy = prepared
    seen: dict[tuple[str, str], Target] = {}
    for target in targets:
        seen.setdefault(device_key(target), target)
    devices = []
    for (bus, ident), target in seen.items():
        choice = policy.choice(bus, ident)
        devices.append({
            "bus": bus,
            "id": ident,
            "name": _plain(device_name(target)),
            "engine": target.entry.engine,
            "effect": policy.effect_for(bus, ident, target.entry.effect),
            "enabled": choice.enabled,
            "gradient": target.entry.engine in GRADIENT_ENGINES,
        })
    return {
        "ok": True,
        "enabled": policy.enabled,
        "solid": theme.solid_hex(),
        "stops": theme.stop_hexes(),
        "devices": devices,
    }


def _device_enabled(target: Target, policy: Behaviour) -> bool:
    bus, ident = device_key(target)
    return policy.choice(bus, ident).enabled


def _with_effect(target: Target, policy: Behaviour) -> Target:
    bus, ident = device_key(target)
    effect = policy.effect_for(bus, ident, target.entry.effect)
    if effect == target.entry.effect:
        return target
    return Target(replace(target.entry, effect=effect), target.hardware, target.openrgb_devices)


def _plain(text: str) -> str:
    cleaned = "".join(
        char for char in text
        if char == " " or (char.isprintable() and char not in "<>&" and ord(char) >= 32)
    )
    return cleaned[:120]


def _apply(theme: Theme, targets: list[Target], dry_run: bool, policy: Behaviour | None = None) -> Report:
    policy = policy or Behaviour()
    if not policy.enabled:
        return Report(["painting is off", f"theme solid {theme.solid_hex()} stops {' '.join(theme.stop_hexes())}"])
    active = []
    skipped = []
    for target in targets:
        if _device_enabled(target, policy):
            active.append(_with_effect(target, policy))
        else:
            skipped.append(target)
    if not active and not skipped:
        return Report([f"theme {theme.solid_hex()} matches no RGB devices"])
    grouped: dict[str, list[Target]] = defaultdict(list)
    for target in active:
        grouped[target.entry.engine].append(target)
    lines = [f"theme solid {theme.solid_hex()} stops {' '.join(theme.stop_hexes())}"]
    for target in skipped:
        lines.append(f"aside {_plain(device_name(target))}")
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


def _settled(report: Report) -> bool:
    """True when hardware was painted and every engine accepted the theme."""
    if report.not_ready:
        return False
    painted = [
        line for line in report.lines
        if not line.startswith("theme solid") and not line.startswith("aside ")
    ]
    return bool(painted) and not any(_failed(line) for line in painted)


def _failed(outcome: str) -> bool:
    return any(word in outcome for word in ("unavailable", "rejected", "missing", "failed", "not ready"))

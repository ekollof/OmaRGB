"""Skip a repeated automatic paint of the palette already on the hardware.

The theme hook and the directory watcher both start an apply for one theme
change, and the hook starts only after the rest of the theme batch. A short
timer misses that second call. Callers that pass debounce skip when the
colours and the matched devices are the ones a successful apply just painted.
A direct apply, and the login hook, paint anyway and refresh that record.
"""

import hashlib
from pathlib import Path

from omargb.catalog import Target
from omargb.theme import Theme

STAMP_NAME = "last-apply"


def unchanged(state: Path, theme: Theme, targets: list[Target], strategy: str = "warmest") -> bool:
    path = state / STAMP_NAME
    try:
        recorded = path.read_text().strip()
    except OSError:
        return False
    return recorded == fingerprint(theme, targets, strategy) and bool(recorded)


def remember(state: Path, theme: Theme, targets: list[Target], strategy: str = "warmest") -> None:
    state.mkdir(parents=True, exist_ok=True)
    (state / STAMP_NAME).write_text(fingerprint(theme, targets, strategy) + "\n")


def fingerprint(theme: Theme, targets: list[Target], strategy: str = "warmest") -> str:
    rows = []
    for target in targets:
        entry = target.entry
        led_counts = dict(target.openrgb_leds)
        devices = " ".join(
            f"{index}:{name}:{led_counts.get(index, 0)}" for index, name in target.openrgb_devices
        )
        rows.append("|".join((
            entry.engine,
            entry.effect,
            entry.direction,
            entry.bus,
            entry.ident,
            target.hardware.ident,
            devices,
        )))
    body = "\n".join([
        theme.solid_hex(),
        " ".join(theme.stop_hexes()),
        strategy,
        theme.choose_hex(strategy),
        *sorted(rows),
    ])
    return hashlib.sha256(body.encode()).hexdigest()

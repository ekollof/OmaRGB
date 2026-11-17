"""Home Assistant lights named in ~/.config/hass.cfg.

Same file wallpaperctl uses. A lamp is painted only when the database matched
it and the light is already on. The call is light.turn_on with rgb_color.
apply.py puts the behaviour strategy's colour in theme.solid for this engine.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

from omargb.catalog import Target
from omargb.hasscfg import HassConfigError, config_path, load
from omargb.theme import Theme


class HomeAssistant:
    name = "homeassistant"

    def apply(self, theme: Theme, targets: list[Target], dry_run: bool) -> str | None:
        lamps = [target.hardware.ident for target in targets if target.hardware.ident]
        if not lamps:
            return None
        colour = theme.solid_hex()
        if dry_run:
            return "homeassistant dry-run " + ", ".join(f"{lamp} {colour}" for lamp in lamps)
        try:
            config = load(config_path(), require_private=True)
        except HassConfigError as error:
            if error.reason == "rejected":
                return "homeassistant rejected the config (permissions)"
            return "homeassistant: config missing"
        allowed = set(config.lamps)
        rgb = list(theme.solid)
        notes: list[str] = []
        for lamp in lamps:
            if lamp not in allowed:
                continue
            outcome = _paint(config.server, config.token, lamp, rgb)
            if outcome == "on":
                notes.append(f"{lamp} {colour}")
            elif outcome == "off":
                notes.append(f"{lamp} off")
            else:
                notes.append(f"{lamp} unavailable")
        if not notes:
            return "homeassistant: config missing"
        if any(note.endswith(" unavailable") for note in notes) and not any(note.endswith(colour) for note in notes):
            return "homeassistant unavailable (" + ", ".join(note.removesuffix(" unavailable") for note in notes if note.endswith(" unavailable")) + ")"
        return "homeassistant " + ", ".join(notes)


def _paint(server: str, token: str, lamp: str, rgb: list[int]) -> str:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    entity = urllib.parse.quote(lamp, safe="")
    try:
        state = _request(f"{server}/api/states/{entity}", headers)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return "unavailable"
    if not isinstance(state, dict):
        return "unavailable"
    if state.get("state") != "on":
        return "off"
    try:
        _request(
            f"{server}/api/services/light/turn_on",
            headers,
            {"entity_id": lamp, "rgb_color": rgb},
        )
    except (urllib.error.URLError, TimeoutError):
        return "unavailable"
    return "on"


def _request(url: str, headers: dict[str, str], body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = response.read().decode()
    if not payload:
        return {}
    return json.loads(payload)

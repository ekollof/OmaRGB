"""The Home Assistant file wallpaperctl already uses.

`~/.config/hass.cfg` holds `[auth]` with `server`, `token`, and `lamp`.
The token is never written into a report. A file other people can read is rejected.
"""

import re
from dataclasses import dataclass
from pathlib import Path

_SECTION = re.compile(r"\[auth\](.*?)(?:\n\[|\Z)", re.S | re.I)
_ENTITY = re.compile(r"^[A-Za-z0-9_]+\.[A-Za-z0-9_]+$")


@dataclass(frozen=True)
class HassConfig:
    server: str
    token: str
    lamps: tuple[str, ...]


class HassConfigError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def config_path() -> Path:
    return Path.home() / ".config" / "hass.cfg"


def load(path: Path, *, require_private: bool = False) -> HassConfig:
    if not path.is_file():
        raise HassConfigError("missing")
    if require_private:
        mode = path.stat().st_mode & 0o777
        if mode & 0o077:
            raise HassConfigError("rejected")
    text = path.read_text(encoding="utf-8", errors="replace")
    found = _SECTION.search(text)
    if not found:
        raise HassConfigError("missing")
    values: dict[str, str] = {}
    for line in found.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    server = values.get("server", "").rstrip("/")
    token = values.get("token", "")
    lamps = tuple(lamp for lamp in (part.strip() for part in values.get("lamp", "").split(",")) if _ENTITY.fullmatch(lamp))
    if not server or not token or not lamps:
        raise HassConfigError("missing")
    return HassConfig(server, token, lamps)

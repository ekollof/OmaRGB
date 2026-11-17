"""Colours from the active Omarchy theme.

colors.toml is the source of truth. keyboard.rgb is a one-colour fallback for
themes that do not ship the 16 ANSI slots. Pastel hexes are rewritten for
light-emitting hardware: the white floor is removed and the strongest remaining
channel is turned fully on.
"""

import math
import re
from dataclasses import dataclass
from pathlib import Path

NEUTRAL_SLOTS = {0, 7, 8, 15}
MIN_PEAK = 24
PEAK = 255
STOPS = 8
# wallpaperctl's rgb_color_strategy names. warmest is what its Home Assistant
# painter uses so a lamp does not take a blue palette line.
STRATEGIES = ("warmest", "least_blue", "most_saturated", "coolest", "brightest")

HEX_KEY = re.compile(r'^(\w+)\s*=\s*"#([0-9a-fA-F]{6})"')
NAMED_SKIP = {"cursor", "icon_mark"}


@dataclass(frozen=True)
class Theme:
    path: Path
    stops: tuple[tuple[int, int, int], ...]
    solid: tuple[int, int, int]
    colours: tuple[tuple[int, int, int], ...] = ()

    def solid_hex(self) -> str:
        return _hex(self.solid)

    def stop_hexes(self) -> list[str]:
        return [_hex(colour) for colour in self.stops]

    def choose(self, strategy: str) -> tuple[int, int, int]:
        """One backlight colour from the theme, scored like wallpaperctl."""
        pool = self.colours or (self.solid,)
        name = strategy if strategy in STRATEGIES else "warmest"
        best = pool[0]
        best_score: float | None = None
        for colour in pool:
            value = _strategy_score(colour, name)
            lower_wins = name in ("least_blue", "coolest")
            if best_score is None or (value < best_score if lower_wins else value > best_score):
                best = colour
                best_score = value
        return best

    def choose_hex(self, strategy: str) -> str:
        return _hex(self.choose(strategy))


def _hex(colour: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*colour)


def parse_rgb(text: str) -> tuple[int, int, int]:
    text = text.removeprefix("#")
    return tuple(int(text[index:index + 2], 16) for index in (0, 2, 4))


def to_led(rgb: tuple[int, int, int]) -> tuple[int, int, int] | None:
    """Palette hue as a backlight colour."""
    floor = min(rgb)
    chroma = tuple(channel - floor for channel in rgb)
    peak = max(chroma)
    if peak < MIN_PEAK:
        return None
    scale = PEAK / peak
    return tuple(min(PEAK, round(channel * scale)) for channel in chroma)


def hue(rgb: tuple[int, int, int]) -> float:
    red, green, blue = (channel / 255 for channel in rgb)

    def linear(channel: float) -> float:
        if channel <= 0.04045:
            return channel / 12.92
        return ((channel + 0.055) / 1.055) ** 2.4

    red, green, blue = linear(red), linear(green), linear(blue)
    long = 0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue
    medium = 0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue
    short = 0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue
    long, medium, short = long ** (1 / 3), medium ** (1 / 3), short ** (1 / 3)
    green_red = 1.9779984951 * long - 2.4285922050 * medium + 0.4505937099 * short
    blue_yellow = 0.0259040371 * long + 0.7827717662 * medium - 0.8086757660 * short
    return math.atan2(blue_yellow, green_red)


def load_theme(path: Path) -> Theme | None:
    if not path.is_file():
        return None
    slots, named = _read_colors(path.read_text())
    sources: list[tuple[int, str]]
    if len(slots) == 16:
        sources = [(index, value) for index, value in slots if index not in NEUTRAL_SLOTS]
    else:
        sources = list(enumerate(named))
    if not sources:
        keyboard = path.parent / "keyboard.rgb"
        if keyboard.is_file():
            text = keyboard.read_text().strip()
            if re.fullmatch(r"#?[0-9a-fA-F]{6}", text):
                sources = [(0, text.removeprefix("#"))]
    converted: list[tuple[float, tuple[int, int, int]]] = []
    colours: list[tuple[int, int, int]] = []
    for _index, text in sources:
        led = to_led(parse_rgb(text))
        if led is None or led in ((0, 0, 0), (255, 255, 255)):
            continue
        colours.append(led)
        converted.append((hue(led), led))
    if not converted:
        return None
    converted.sort()
    unique: list[tuple[float, tuple[int, int, int]]] = []
    for item in converted:
        if unique and abs(item[0] - unique[-1][0]) < 0.18 and max(
            abs(left - right) for left, right in zip(item[1], unique[-1][1])
        ) < 36:
            continue
        unique.append(item)
    chosen = _spread(unique, STOPS)
    chosen.sort()
    stops = tuple(colour for _hue, colour in chosen)
    solid = max(stops, key=lambda colour: max(colour) - min(colour))
    return Theme(path=path, stops=stops, solid=solid, colours=tuple(colours))


def _strategy_score(colour: tuple[int, int, int], strategy: str) -> float:
    red, green, blue = colour
    if strategy == "least_blue":
        return blue - ((red + green) / 2)
    if strategy == "most_saturated":
        return float(max(colour) - min(colour))
    if strategy == "brightest":
        return (red + green + blue) / 3
    # warmest scores high when red leads blue. coolest uses the same score and keeps the low one.
    return red - blue + (red - green) / 2


def _read_colors(text: str) -> tuple[list[tuple[int, str]], list[str]]:
    found: dict[int, str] = {}
    named: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        match = HEX_KEY.match(line.strip())
        if not match:
            continue
        key, value = match.group(1), match.group(2).lower()
        slot = re.fullmatch(r"color(\d+)", key)
        if slot and int(slot.group(1)) < 16:
            found[int(slot.group(1))] = value
            continue
        if key in NAMED_SKIP or "background" in key or "foreground" in key:
            continue
        if value in seen:
            continue
        seen.add(value)
        named.append(value)
    slots = [(index, found[index]) for index in range(16) if index in found]
    return slots, named


def spread(stops: list[tuple[int, int, int]], count: int) -> list[tuple[int, int, int]]:
    """Place the theme stops across `count` LEDs."""
    if count <= 0:
        return []
    if len(stops) < 2:
        return [stops[0]] * count
    result = []
    for index in range(count):
        position = index / (count - 1) * (len(stops) - 1)
        stop = min(int(position), len(stops) - 2)
        fraction = position - stop
        left, right = stops[stop], stops[stop + 1]
        result.append(tuple(
            round(left[channel] + (right[channel] - left[channel]) * fraction) for channel in range(3)
        ))
    return result


def _spread(items: list, count: int) -> list:
    if len(items) <= count:
        return items
    step = len(items) / count
    return [items[min(len(items) - 1, int(index * step))] for index in range(count)]


def default_colors_path() -> Path:
    return Path.home() / ".local/state/omarchy/current/theme/colors.toml"

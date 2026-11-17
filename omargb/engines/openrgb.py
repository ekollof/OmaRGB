"""OpenRGB devices, painted through the local server the same way its client is.

Protocol 4 on 127.0.0.1:6742. The 1.1 server still answers that description
layout. A later protocol pushes its own name and waits for acknowledgements,
which this client does not need. A device with a per-LED mode and more than
one LED gets the theme stops. A keyboard matrix is painted left to right, one
colour per column, the way the Vanguard runs side to side. A strip with no
matrix follows the LED list. A device with no LED list gets one colour in
its Static mode.
"""

import socket
import struct
from dataclasses import dataclass, replace

from omargb.catalog import Target
from omargb.theme import Theme, spread

HOST = "127.0.0.1"
PORT = 6742
PROTOCOL = 4
CLIENT_NAME = b"omargb\x00"
PER_LED = 1
MODE_SPECIFIC = 2
KEYBOARD = 5
HAS_BRIGHTNESS = 1 << 4

REQUEST_CONTROLLER_COUNT = 0
REQUEST_CONTROLLER_DATA = 1
REQUEST_PROTOCOL_VERSION = 40
SET_CLIENT_NAME = 50
UPDATE_LEDS = 1050
SET_CUSTOM_MODE = 1100
UPDATE_MODE = 1101


@dataclass(frozen=True)
class Mode:
    index: int
    name: str
    value: int
    flags: int
    speed_min: int
    speed_max: int
    brightness_min: int
    brightness_max: int
    colors_min: int
    colors_max: int
    speed: int
    brightness: int
    direction: int
    color_mode: int
    colours: tuple[tuple[int, int, int], ...]

    @property
    def per_led(self) -> bool:
        return self.color_mode == PER_LED


@dataclass(frozen=True)
class Controller:
    index: int
    name: str
    leds: int
    modes: tuple[Mode, ...]
    # (column, row) for each LED when the device has a keyboard matrix.
    places: tuple[tuple[int, int] | None, ...] = ()
    keyboard: bool = False

    @property
    def per_led_mode(self) -> Mode | None:
        return next((mode for mode in self.modes if mode.per_led), None)

    @property
    def gradient_count(self) -> int:
        if self.leds > 1 and self.per_led_mode is not None:
            return self.leds
        return 0


class OpenRgb:
    name = "openrgb"

    def apply(self, theme: Theme, targets: list[Target], dry_run: bool) -> str:
        jobs = [
            (index, name, counts.get(index, 0), target.entry.effect)
            for target in targets
            for counts in (dict(target.openrgb_leds),)
            for index, name in target.openrgb_devices
        ]
        if not jobs:
            return "openrgb: nothing addressed"
        if dry_run:
            return "openrgb dry-run " + ", ".join(
                _note(index, name, effect, leds, theme) for index, name, leds, effect in jobs
            )
        opened = session()
        if opened is None:
            return "openrgb: not ready"
        link, found = opened
        try:
            live = {controller.index: controller for controller in found}
            notes: list[str] = []
            used: set[int] = set()
            for index, name, _leds, effect in jobs:
                controller = _pick(live, used, index, name)
                if controller is None:
                    continue
                if controller.leds >= 1 and controller.per_led_mode is not None:
                    link.paint(controller, _colours(theme, effect, controller))
                    notes.append(_note(controller.index, controller.name, effect, controller.leds, theme))
                elif link.paint_static(controller, theme.solid):
                    notes.append(_note(controller.index, controller.name, "solid", 0, theme))
            if not notes:
                return "openrgb: nothing addressed"
            return "openrgb " + ", ".join(notes)
        except OSError:
            return "openrgb: not ready"
        finally:
            link.close()


def list_devices(opener=None) -> list[tuple[int, str, int, bool]]:
    """Indexed devices from the OpenRGB server.

    The third field is the LED count when the device has a per-LED mode and
    more than one LED, otherwise 0. The fourth field is true for a keyboard.
    A server that is not answering yields an empty list, so the other engines
    still run.
    """
    opened = session(opener or connect)
    if not isinstance(opened, tuple):
        return []
    link, found = opened
    try:
        return [
            (controller.index, controller.name, controller.gradient_count, controller.keyboard)
            for controller in found
        ]
    finally:
        link.close()


class Link:
    """One TCP session. Writes are not answered on protocol 4, so paint does not read."""

    def __init__(self, sock: socket.socket):
        self.sock = sock

    def close(self) -> None:
        self.sock.close()

    def send(self, dev: int, pkt: int, payload: bytes = b"") -> None:
        self.sock.sendall(struct.pack("<4sIII", b"ORGB", dev, pkt, len(payload)) + payload)

    def read(self) -> tuple[int, int, bytes]:
        magic, dev, pkt, size = struct.unpack("<4sIII", _recv_exact(self.sock, 16))
        if magic != b"ORGB":
            raise ValueError("openrgb: bad packet")
        return pkt, dev, _recv_exact(self.sock, size) if size else b""

    def request(self, dev: int, pkt: int, payload: bytes = b"") -> tuple[int, int, bytes]:
        self.send(dev, pkt, payload)
        return self.read()

    def controllers(self) -> list[Controller]:
        _pkt, _dev, payload = self.request(0, REQUEST_CONTROLLER_COUNT, b"")
        if len(payload) < 4:
            raise ValueError("openrgb: short controller count")
        count = struct.unpack_from("<I", payload)[0]
        found = []
        for index in range(count):
            _pkt, dev, blob = self.request(index, REQUEST_CONTROLLER_DATA, struct.pack("<I", PROTOCOL))
            found.append(parse_controller(blob, dev))
        return found

    def paint(self, controller: Controller, colours: list[tuple[int, int, int]]) -> None:
        """Per-LED colours. A brightness range is set to its maximum first."""
        mode = controller.per_led_mode
        if mode is None:
            return
        if mode.flags & HAS_BRIGHTNESS and mode.brightness_max != mode.brightness_min:
            self.send(controller.index, UPDATE_MODE, pack_update_mode(mode, mode.brightness_max))
        else:
            self.send(controller.index, SET_CUSTOM_MODE, b"")
        self.send(controller.index, UPDATE_LEDS, pack_leds(colours))

    def paint_static(self, controller: Controller, colour: tuple[int, int, int]) -> bool:
        """One mode colour, for a controller that has no LED list. Returns whether a packet was sent."""
        mode = static_mode(controller)
        if mode is None:
            return False
        bright = mode.brightness
        if mode.flags & HAS_BRIGHTNESS and mode.brightness_max != mode.brightness_min:
            bright = mode.brightness_max
        painted = replace(mode, colours=(colour,) * max(mode.colors_min, 1))
        self.send(controller.index, UPDATE_MODE, pack_update_mode(painted, bright))
        return True


def connect(host: str = HOST, port: int = PORT, timeout: float = 5) -> Link:
    sock = socket.create_connection((host, port), timeout)
    sock.settimeout(timeout)
    link = Link(sock)
    try:
        greet(link)
    except Exception:
        link.close()
        raise
    return link


def greet(link: Link) -> None:
    link.request(0, REQUEST_PROTOCOL_VERSION, struct.pack("<I", PROTOCOL))
    link.send(0, SET_CLIENT_NAME, CLIENT_NAME)


def session(opener=connect):
    """Open a session and read the controller list. None when the server is down.

    The server's per-controller thread can miss a wakeup and never answer.
    One fresh connection is the retry. A parse error closes the socket and
    comes back as None so one bad description cannot stop the other engines.
    """
    for _attempt in range(2):
        link = None
        try:
            link = opener()
            return link, link.controllers()
        except TimeoutError:
            if link is not None:
                link.close()
        except (OSError, ValueError, struct.error):
            if link is not None:
                link.close()
            return None
    return None


class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.at = 0

    def take(self, fmt: str):
        size = struct.calcsize(fmt)
        if self.at + size > len(self.data):
            raise ValueError("openrgb: description ended early")
        value = struct.unpack_from(fmt, self.data, self.at)
        self.at += size
        return value[0] if len(value) == 1 else value

    def string(self) -> str:
        length = self.take("<H")
        if length < 1 or self.at + length > len(self.data):
            raise ValueError("openrgb: bad string")
        raw = self.data[self.at:self.at + length]
        self.at += length
        return raw.split(b"\x00", 1)[0].decode("utf-8", "replace")

    def skip(self, size: int) -> None:
        if size < 0 or self.at + size > len(self.data):
            raise ValueError("openrgb: description ended early")
        self.at += size


def parse_controller(blob: bytes, index: int) -> Controller:
    reader = Reader(blob)
    data_size = reader.take("<I")
    if data_size != len(blob):
        raise ValueError("openrgb: description size does not match")
    kind = reader.take("<i")
    name = reader.string()
    for _field in range(5):
        reader.string()
    num_modes = reader.take("<H")
    reader.take("<i")
    modes = tuple(_mode(reader, mode_index) for mode_index in range(num_modes))
    grids = []
    for _index in range(reader.take("<H")):
        grid = _zone(reader)
        if grid is not None:
            grids.append(grid)
    num_leds = reader.take("<H")
    for _led in range(num_leds):
        reader.string()
        reader.take("<I")
    colours = reader.take("<H")
    reader.skip(4 * colours)
    if reader.at != len(blob):
        raise ValueError("openrgb: description was not fully read")
    return Controller(index, name, num_leds, modes, _places(tuple(grids), num_leds), kind == KEYBOARD)


def pack_update_mode(mode: Mode, brightness: int) -> bytes:
    description = _pack_string(mode.name)
    description += struct.pack(
        "<i11IH",
        mode.value,
        mode.flags,
        mode.speed_min,
        mode.speed_max,
        mode.brightness_min,
        mode.brightness_max,
        mode.colors_min,
        mode.colors_max,
        mode.speed,
        brightness,
        mode.direction,
        mode.color_mode,
        len(mode.colours),
    )
    description += b"".join(struct.pack("<BBBx", *colour) for colour in mode.colours)
    rest = struct.pack("<i", mode.index) + description
    return struct.pack("<I", 4 + len(rest)) + rest


def pack_leds(colours: list[tuple[int, int, int]]) -> bytes:
    body = struct.pack("<H", len(colours))
    body += b"".join(struct.pack("<BBBx", red, green, blue) for red, green, blue in colours)
    return struct.pack("<I", 4 + len(body)) + body


def _mode(reader: Reader, index: int) -> Mode:
    name = reader.string()
    value = reader.take("<i")
    flags = reader.take("<I")
    numbers = reader.take("<8I")
    direction = reader.take("<I")
    color_mode = reader.take("<I")
    num_colours = reader.take("<H")
    colours = tuple(reader.take("<BBBx") for _colour in range(num_colours))
    return Mode(
        index,
        name,
        value,
        flags,
        numbers[0],
        numbers[1],
        numbers[2],
        numbers[3],
        numbers[4],
        numbers[5],
        numbers[6],
        numbers[7],
        direction,
        color_mode,
        colours,
    )


def _zone(reader: Reader) -> tuple[int, int, tuple[int, ...]] | None:
    reader.string()
    reader.take("<iIII")
    matrix = reader.take("<H")
    grid = None
    if matrix:
        height, width = reader.take("<II")
        grid = (height, width, tuple(reader.take("<I") for _cell in range(height * width)))
    for _segment in range(reader.take("<H")):
        reader.string()
        reader.take("<iII")
    return grid


def _places(grids: tuple[tuple[int, int, tuple[int, ...]], ...], led_count: int) -> tuple[tuple[int, int] | None, ...]:
    """Column and row of each LED. Empty when the device has no matrix."""
    if not grids:
        return ()
    places: list[tuple[int, int] | None] = [None] * led_count
    for _height, width, cells in grids:
        if width == 0:
            continue
        for offset, led in enumerate(cells):
            if led == 0xFFFFFFFF or led >= led_count or places[led] is not None:
                continue
            places[led] = (offset % width, offset // width)
    if not any(place is not None for place in places):
        return ()
    return tuple(places)


def _pack_string(text: str) -> bytes:
    raw = text.encode("utf-8") + b"\x00"
    return struct.pack("<H", len(raw)) + raw


def static_mode(controller: Controller) -> Mode | None:
    """A one-colour hardware mode, preferring the one named Static."""
    matches = [
        mode
        for mode in controller.modes
        if mode.color_mode == MODE_SPECIFIC and mode.colors_min == 1 and mode.colors_max == 1
    ]
    for mode in matches:
        if mode.name.casefold() == "static":
            return mode
    return matches[0] if matches else None


def _note(index: int, name: str, effect: str, leds: int, theme: Theme) -> str:
    if effect == "gradient" and leds > 1 and theme.stops:
        return f"{index}:{name} gradient"
    return f"{index}:{name} {theme.solid_hex()}"


def _colours(theme: Theme, effect: str, controller: Controller) -> list[tuple[int, int, int]]:
    if effect == "gradient" and controller.leds > 1 and theme.stops:
        if controller.places:
            across = _across(list(theme.stops), controller.places, controller.leds)
            if across is not None:
                return across
        return spread(list(theme.stops), controller.leds)
    return [theme.solid] * controller.leds


def _across(
    stops: list[tuple[int, int, int]],
    places: tuple[tuple[int, int] | None, ...],
    led_count: int,
) -> list[tuple[int, int, int]] | None:
    """One colour per keyboard column, from the left of the board to the right."""
    columns = [place[0] for place in places if place is not None]
    if len(columns) < 2:
        return None
    left, right = min(columns), max(columns)
    if left == right:
        return None
    palette = spread(stops, right - left + 1)
    colours = [palette[0]] * led_count
    for index, place in enumerate(places):
        if place is not None:
            colours[index] = palette[place[0] - left]
    return colours


def _pick(live: dict[int, Controller], used: set[int], index: int, name: str) -> Controller | None:
    controller = live.get(index)
    if controller is not None and controller.name == name and index not in used:
        used.add(index)
        return controller
    for candidate in live.values():
        if candidate.name == name and candidate.index not in used:
            used.add(candidate.index)
            return candidate
    return None


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    buf = b""
    while len(buf) < size:
        chunk = sock.recv(size - len(buf))
        if not chunk:
            raise ConnectionError("openrgb: connection closed")
        buf += chunk
    return buf

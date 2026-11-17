"""Sound BlasterX Vanguard K08 lighting over hidraw.

The firmware stores an 8192-byte map. LED i's primary colour is three bytes at
0x09 + i*50 + 2. The map is read back during the handshake (report 0x05, data
at offset 4) and only those RGB bytes are changed, so the macro table at
0x1960 stays as the keyboard has it. Each 2048-byte chunk then needs about
350 ms or the firmware keeps the previous map.
"""

import glob
import os
import time

from omargb.catalog import Target
from omargb.theme import Theme

CHUNK = 2048
ENTRY = 0x09
STRIDE = 50
CHUNK_SETTLE_S = 0.35
CMD_SETTLE_S = 0.12

ZONES = [
    [0, 1, 13, 14, 15, 29, 30, 31, 44, 45, 59, 60, 74, 75, 76, 61],
    [2, 3, 16, 17, 18, 32, 33, 34, 46, 47, 48, 62, 63, 64, 77],
    [4, 5, 6, 19, 20, 21, 35, 36, 37, 49, 50, 51, 65, 66, 67, 80],
    [7, 8, 22, 23, 24, 38, 39, 40, 52, 53, 54, 68, 69, 70, 84],
    [9, 10, 11, 12, 25, 26, 28, 41, 42, 43, 55, 56, 58, 71, 73, 85, 86, 87, 57],
    [109, 117, 125, 100, 99, 98, 108, 107, 106, 115, 116, 124, 123],
    [97, 96, 95, 94, 105, 104, 103, 102, 113, 112, 111, 114, 120, 119, 118, 122, 121],
    [126],
]


class VanguardK08:
    name = "vanguard_k08"

    def apply(self, theme: Theme, targets: list[Target], dry_run: bool) -> str | None:
        if not targets:
            return None
        effect = targets[0].entry.effect
        stops = list(theme.stops if effect == "gradient" else (theme.solid, theme.solid))
        if dry_run:
            return "vanguard_k08 dry-run " + " ".join(_hex(colour) for colour in theme.stops)
        path = find_hidraw()
        if path is None:
            return "vanguard_k08: lighting interface not ready"
        import fcntl

        fd = os.open(path, os.O_RDWR)
        try:
            block = read_map(fd, fcntl)
            ordered = [led for zone in ZONES for led in zone]
            for led, colour in zip(ordered, gradient(stops, len(ordered))):
                paint(block, led, colour)
            write_map(fd, fcntl, block)
        finally:
            os.close(fd)
        return "vanguard_k08 " + " ".join(_hex(colour) for colour in theme.stops)


def find_hidraw() -> str | None:
    paths = sorted(glob.glob("/dev/input/by-id/*Vanguard*if01-hidraw"))
    return paths[0] if paths else None


def gradient(stops: list[tuple[int, int, int]], count: int) -> list[tuple[int, int, int]]:
    if len(stops) < 2:
        return [stops[0]] * count
    result = []
    for index in range(count):
        position = index / (count - 1) * (len(stops) - 1)
        stop = min(int(position), len(stops) - 2)
        fraction = position - stop
        left, right = stops[stop], stops[stop + 1]
        result.append(tuple(round(left[channel] + (right[channel] - left[channel]) * fraction) for channel in range(3)))
    return result


def paint(block: bytearray, led: int, colour: tuple[int, int, int]) -> None:
    offset = ENTRY + led * STRIDE + 2
    block[offset:offset + 3] = bytes(colour)


def read_map(fd: int, fcntl) -> bytearray:
    _command(fd, fcntl, [0xC4, 0x08, 0, 0, 0, 0, 0, 0])
    _get(fd, fcntl, 0x0C, 9)
    chunks = []
    for slot in range(4):
        _command(fd, fcntl, [0xC4, 0x0C, slot, 0, 0, 0, 0, 0])
        report = _get(fd, fcntl, 0x05, 5 + CHUNK)
        chunks.append(report[4:4 + CHUNK])
    _command(fd, fcntl, [0xC4, 0x11, 0, 0, 0, 0, 0, 0])
    _get(fd, fcntl, 0x07, 261)
    block = bytearray(b"".join(chunks))
    if len(block) != CHUNK * 4:
        raise OSError("keyboard returned a short lighting map")
    return block


def write_map(fd: int, fcntl, block: bytearray) -> None:
    for slot in range(4):
        data = bytes(block[slot * CHUNK:(slot + 1) * CHUNK])
        checksum = (-sum(data)) & 0xFF
        _set(fd, fcntl, bytes([0x05, 0x00, slot, checksum]) + data + b"\x00")
        time.sleep(CHUNK_SETTLE_S)
    _command(fd, fcntl, [0xC4, 0x00, 0, 0, 0, 0, 0, 0])


def _ioctl(nr: int, size: int) -> int:
    return (3 << 30) | ((size & 0x3FFF) << 16) | (ord("H") << 8) | nr


def _set(fd: int, fcntl, data: bytes) -> None:
    fcntl.ioctl(fd, _ioctl(0x06, len(data)), bytearray(data), True)


def _get(fd: int, fcntl, report: int, size: int) -> bytes:
    buffer = bytearray(size)
    buffer[0] = report
    fcntl.ioctl(fd, _ioctl(0x07, len(buffer)), buffer, True)
    return bytes(buffer)


def _command(fd: int, fcntl, payload: list[int]) -> None:
    packet = bytearray(9)
    packet[0] = 0x0C
    packet[1:1 + len(payload)] = bytes(payload)
    _set(fd, fcntl, packet)
    time.sleep(CMD_SETTLE_S)


def _hex(colour: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*colour)

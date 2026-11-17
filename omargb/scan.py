"""USB, PCI, and firmware board identifiers."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Hardware:
    bus: str
    ident: str
    name: str


def scan(root: Path | None = None) -> list[Hardware]:
    root = root or Path("/")
    found: list[Hardware] = []
    found.extend(_usb(root))
    found.extend(_pci(root))
    found.extend(_dmi(root))
    return found


def _usb(root: Path) -> list[Hardware]:
    base = root / "sys/bus/usb/devices"
    found = []
    if not base.is_dir():
        return found
    for device in sorted(base.iterdir()):
        vendor = _text(device / "idVendor")
        product = _text(device / "idProduct")
        if not vendor or not product:
            continue
        name = _text(device / "product") or _text(device / "manufacturer") or ""
        found.append(Hardware("usb", f"{vendor.lower()}:{product.lower()}", name))
    return found


def _pci(root: Path) -> list[Hardware]:
    base = root / "sys/bus/pci/devices"
    found = []
    if not base.is_dir():
        return found
    for device in sorted(base.iterdir()):
        vendor = _hex_id(_text(device / "vendor"))
        product = _hex_id(_text(device / "device"))
        if not vendor or not product:
            continue
        found.append(Hardware("pci", f"{vendor}:{product}", device.name))
    return found


def _dmi(root: Path) -> list[Hardware]:
    """Board, product family, and product name.

    Omarchy's ROG check is sys_vendor plus "ROG" anywhere in product_family.
    Its Framework 16 check is sys_vendor "Framework" plus "Laptop 16" in
    product_name or product_family. The board pair stays so motherboard
    lighting can match board_name.
    """
    base = root / "sys/class/dmi/id"
    found: list[Hardware] = []
    board_vendor = _text(base / "board_vendor")
    board_name = _text(base / "board_name")
    if board_vendor or board_name:
        found.append(Hardware("dmi", f"{board_vendor}:{board_name}", board_name))
    sys_vendor = _text(base / "sys_vendor")
    for label in (_text(base / "product_family"), _text(base / "product_name")):
        if sys_vendor and label:
            found.append(Hardware("dmi", f"{sys_vendor}:{label}", label))
    return found


def _text(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def _hex_id(value: str) -> str:
    if not value:
        return ""
    return f"{int(value, 16):04x}"

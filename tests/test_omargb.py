#!/usr/bin/env python3
"""Matcher and palette tests. No hardware."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from omargb.apply import run
from omargb.catalog import load_database, match
from omargb.engines.framework16 import qmk_hue_saturation
from omargb.scan import Hardware, scan
from omargb.theme import load_theme, parse_rgb, to_led

PURPLE = """
mode = "dark"
accent = "#d88cbb"
color0 = "#000002"
color1 = "#ba7da2"
color2 = "#fea2ae"
color3 = "#ffc9e5"
color4 = "#916ba9"
color5 = "#d18dd1"
color6 = "#dac5ff"
color7 = "#fee6dc"
color8 = "#5d6066"
color9 = "#d88cbb"
color10 = "#ffaec0"
color11 = "#ffc2e6"
color12 = "#aa7cc8"
color13 = "#f19bf2"
color14 = "#f3d7ff"
color15 = "#fbf2fb"
"""


class PaletteTest(unittest.TestCase):
    def test_white_floor_is_removed(self):
        self.assertEqual(to_led(parse_rgb("dac5ff")), (0x5C, 0x00, 0xFF))
        self.assertEqual(to_led(parse_rgb("ffaec0")), (0xFF, 0x00, 0x39))
        self.assertIsNone(to_led(parse_rgb("000002")))
        self.assertIsNone(to_led((255, 255, 255)))

    def test_theme_stops_are_full_rgb(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "colors.toml"
            path.write_text(PURPLE)
            theme = load_theme(path)
        self.assertIsNotNone(theme)
        for colour in theme.stops:
            self.assertEqual(min(colour), 0)
            self.assertEqual(max(colour), 255)
        self.assertIn((0x5C, 0x00, 0xFF), theme.stops)
        self.assertEqual(min(theme.solid), 0)
        self.assertEqual(max(theme.solid), 255)

    def test_framework_hue_matches_omarchy(self):
        self.assertEqual(qmk_hue_saturation(parse_rgb("7aa2f7")), (156, 129))
        self.assertEqual(qmk_hue_saturation(parse_rgb("808080")), (0, 0))


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.database = Path(__file__).resolve().parent.parent / "share" / "devices.toml"
        self.entries = load_database(self.database)

    def test_usb_and_openrgb_selection(self):
        hardware = [
            Hardware("usb", "041e:3126", "Vanguard K08"),
            Hardware("usb", "1532:0099", "Basilisk"),
            Hardware("usb", "1b1c:0c10", "Commander"),
            Hardware("usb", "1234:5678", "Unlisted"),
            Hardware("dmi", "Micro-Star International Co., Ltd.:X470 GAMING PLUS MAX (MS-7B79)", "board"),
        ]
        openrgb = [
            (0, "Corsair Vengeance RGB Pro DDR4"),
            (1, "Corsair Vengeance RGB Pro DDR4"),
            (4, "Corsair Commander Pro"),
            (5, "Razer Basilisk V3"),
            (6, "MSI X470 GAMING PLUS MAX (MS-7B79)"),
            (7, "Some Other Lamp"),
        ]
        targets = match(self.entries, hardware, openrgb)
        engines = {target.entry.engine for target in targets}
        self.assertIn("vanguard_k08", engines)
        self.assertIn("openlinkhub", engines)
        self.assertNotIn("asus_rog", engines)
        names = [target.entry.name for target in targets]
        self.assertNotIn("Unlisted", names)
        painted = [name for target in targets for _index, name in target.openrgb_devices]
        self.assertIn("Razer Basilisk V3", painted)
        self.assertIn("Corsair Commander Pro", painted)
        self.assertEqual(painted.count("Corsair Vengeance RGB Pro DDR4"), 2)
        self.assertNotIn("Some Other Lamp", painted)

    def test_rog_matches_product_family_not_board_name(self):
        hardware = [
            Hardware("dmi", "ASUSTeK COMPUTER INC.:GA503RS", "board"),
            Hardware("dmi", "ASUSTeK COMPUTER INC.:ROG Zephyrus G15", "family"),
        ]
        names = [target.entry.name for target in match(self.entries, hardware, [])]
        self.assertIn("ASUS ROG keyboard", names)

    def test_framework_matches_laptop_16_product_name(self):
        hardware = [
            Hardware("dmi", "Framework:FRANMZCP07", "board"),
            Hardware("dmi", "Framework:Laptop 16 (AMD Ryzen 7040 Series)", "product"),
        ]
        names = [target.entry.name for target in match(self.entries, hardware, [])]
        self.assertIn("Framework Laptop 16", names)

    def test_other_asus_stays_dark(self):
        hardware = [
            Hardware("dmi", "ASUSTeK COMPUTER INC.:UX3405MA", "board"),
            Hardware("dmi", "ASUSTeK COMPUTER INC.:Zenbook", "family"),
            Hardware("dmi", "ASUSTeK COMPUTER INC.:Zenbook 14", "product"),
        ]
        engines = {target.entry.engine for target in match(self.entries, hardware, [])}
        self.assertNotIn("asus_rog", engines)

    def test_plan_uses_only_the_database(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            device = root / "sys/bus/usb/devices/5-7"
            device.mkdir(parents=True)
            (device / "idVendor").write_text("041e\n")
            (device / "idProduct").write_text("3126\n")
            (device / "product").write_text("Vanguard\n")
            colors = root / "colors.toml"
            colors.write_text(PURPLE)
            report = run(
                colors=colors,
                database=self.database,
                dry_run=True,
                root=root,
                openrgb_devices=[],
            )
        text = report.text()
        self.assertIn("vanguard_k08 dry-run", text)
        self.assertNotIn("openrgb", text)
        self.assertFalse(report.not_ready)


class ScanTest(unittest.TestCase):
    def test_reads_sysfs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            usb = root / "sys/bus/usb/devices/1-1"
            usb.mkdir(parents=True)
            (usb / "idVendor").write_text("041e\n")
            (usb / "idProduct").write_text("3126\n")
            pci = root / "sys/bus/pci/devices/0000:29:00.0"
            pci.mkdir(parents=True)
            (pci / "vendor").write_text("0x1002\n")
            (pci / "device").write_text("0x73bf\n")
            dmi = root / "sys/class/dmi/id"
            dmi.mkdir(parents=True)
            (dmi / "board_vendor").write_text("Example\n")
            (dmi / "board_name").write_text("Board\n")
            (dmi / "sys_vendor").write_text("Framework\n")
            (dmi / "product_family").write_text("Laptop 16\n")
            (dmi / "product_name").write_text("Laptop 16 (AMD Ryzen 7040 Series)\n")
            found = {(item.bus, item.ident) for item in scan(root)}
        self.assertIn(("usb", "041e:3126"), found)
        self.assertIn(("pci", "1002:73bf"), found)
        self.assertIn(("dmi", "Example:Board"), found)
        self.assertIn(("dmi", "Framework:Laptop 16"), found)
        self.assertIn(("dmi", "Framework:Laptop 16 (AMD Ryzen 7040 Series)"), found)


if __name__ == "__main__":
    unittest.main()

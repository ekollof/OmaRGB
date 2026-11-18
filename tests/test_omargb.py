#!/usr/bin/env python3
"""Matcher and palette tests. No hardware."""

import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from omargb.apply import PALETTE_PASSES, Report, _apply, describe, run
from omargb.debounce import fingerprint, remember
from omargb.behaviour import Behaviour, load, save
from omargb.console import present_lines, status_mark
from omargb.catalog import Entry, Target, load_database, match
from omargb.engines.framework16 import qmk_hue_saturation
from omargb.engines.vanguard_k08 import ZONES, led_colours
from omargb.engines.homeassistant import HomeAssistant
from omargb.engines.openrgb import (
    Controller,
    Link,
    Mode,
    OpenRgb,
    greet,
    list_devices,
    pack_leds,
    pack_update_mode,
    parse_controller,
    _colours,
)
from omargb.scan import Hardware, scan
from omargb.theme import Theme, load_theme, parse_rgb, to_led

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


class ConsoleTest(unittest.TestCase):
    def test_status_mark_follows_the_report(self):
        ready = Report(["theme solid #5c00ff stops #5c00ff", "vanguard_k08 dry-run #5c00ff"])
        self.assertEqual(status_mark(ready, "plan"), ("32", "Ready"))
        self.assertEqual(status_mark(ready, "apply"), ("32", "Done"))
        self.assertEqual(status_mark(Report(["vanguard_k08: lighting interface not ready"], not_ready=True), "apply"), ("31", "Not ready"))
        self.assertEqual(status_mark(Report(["asus_rog: asusctl missing"]), "apply"), ("31", "Failed"))
        self.assertEqual(status_mark(Report(["no theme colours to apply"]), "apply"), ("90", "Nothing to paint"))

    def test_card_fits_a_long_openrgb_list(self):
        lines = [
            "theme solid #0091ff stops #0091ff #006bff #003fff #3e00ff #9100ff #fa00ff",
            "vanguard_k08 #0091ff #006bff #003fff #3e00ff #9100ff #fa00ff",
            "openrgb 5:Razer Basilisk V3 #0091ff, 6:MSI X470 GAMING PLUS MAX (MS-7B79) #0091ff, "
            "0:Corsair Vengeance RGB Pro DDR4 #0091ff, 1:Corsair Vengeance RGB Pro DDR4 #0091ff",
            "openlinkhub Corsair Commander PRO #0091ff",
        ]
        shown = present_lines(lines, 36)
        self.assertTrue(all(len(row) <= 36 for row in shown))
        self.assertIn("solid  #0091ff", shown)
        self.assertIn("vanguard_k08", shown)
        self.assertIn("  gradient", shown)
        self.assertIn("  Razer Basilisk V3", shown)
        self.assertIn("  Corsair Vengeance RGB Pro DDR4 ×2", shown)
        self.assertNotIn("5:", "\n".join(shown))
        self.assertIn("  Corsair Commander PRO", shown)


class DebounceTest(unittest.TestCase):
    def test_a_repeat_of_the_same_palette_does_not_paint(self):
        theme = Theme(Path("colors.toml"), ((0, 145, 255),), (0, 145, 255))
        entry = Entry("usb", "041e:3126", "K08", "vanguard_k08", "gradient", "", "")
        target = Target(entry, Hardware("usb", "041e:3126", "K08"))
        calls: list[bool] = []

        class Engine:
            name = "vanguard_k08"

            def apply(self, theme, targets, dry_run):
                calls.append(dry_run)
                return "vanguard_k08 #0091ff"

        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            colors = state / "colors.toml"
            colors.write_text("color\n")
            with (
                patch("omargb.apply.load_theme", return_value=theme),
                patch("omargb.apply.load_database", return_value=[entry]),
                patch("omargb.apply.scan", return_value=[target.hardware]),
                patch("omargb.apply.match", return_value=[target]),
                patch("omargb.apply.ENGINES", {"vanguard_k08": Engine()}),
            ):
                first = run(colors=colors, state=state)
                second = run(colors=colors, debounce=True, state=state)
                forced = run(colors=colors, state=state)
                planned = run(colors=colors, dry_run=True, debounce=True, state=state)
        self.assertEqual(calls, [False, False, True])
        self.assertIn("#0091ff", first.text())
        self.assertEqual(second.text(), "unchanged solid #0091ff")
        self.assertIn("vanguard_k08", forced.text())
        self.assertIn("vanguard_k08", planned.text())
        self.assertEqual(status_mark(second, "apply"), ("32", "Done"))

    def test_a_failed_paint_is_retried(self):
        theme = Theme(Path("colors.toml"), ((0, 145, 255),), (0, 145, 255))
        entry = Entry("usb", "041e:3126", "K08", "vanguard_k08", "gradient", "", "")
        target = Target(entry, Hardware("usb", "041e:3126", "K08"))
        calls: list[str] = []

        class Engine:
            name = "vanguard_k08"

            def apply(self, theme, targets, dry_run):
                calls.append("paint")
                if len(calls) == 1:
                    return "vanguard_k08: lighting interface not ready"
                return "vanguard_k08 #0091ff"

        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            colors = state / "colors.toml"
            colors.write_text("color\n")
            with (
                patch("omargb.apply.load_theme", return_value=theme),
                patch("omargb.apply.load_database", return_value=[entry]),
                patch("omargb.apply.scan", return_value=[target.hardware]),
                patch("omargb.apply.match", return_value=[target]),
                patch("omargb.apply.ENGINES", {"vanguard_k08": Engine()}),
            ):
                first = run(colors=colors, debounce=True, state=state)
                second = run(colors=colors, debounce=True, state=state)
        self.assertTrue(first.not_ready)
        self.assertEqual(calls, ["paint", "paint"])
        self.assertIn("vanguard_k08 #0091ff", second.text())

    def test_a_palette_replaced_during_the_paint_is_the_one_remembered(self):
        blue = Theme(Path("colors.toml"), ((0, 145, 255),), (0, 145, 255))
        red = Theme(Path("colors.toml"), ((255, 40, 0),), (255, 40, 0))
        entry = Entry("usb", "041e:3126", "K08", "vanguard_k08", "gradient", "", "")
        target = Target(entry, Hardware("usb", "041e:3126", "K08"))
        loaded: list[str] = []
        painted: list[str] = []

        def load(_path):
            # First read is blue. The check after that paint, and every later read, is red.
            loaded.append("read")
            return blue if len(loaded) == 1 else red

        class Engine:
            name = "vanguard_k08"

            def apply(self, theme, targets, dry_run):
                painted.append(theme.solid_hex())
                return f"vanguard_k08 {theme.solid_hex()}"

        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            colors = state / "colors.toml"
            colors.write_text("color\n")
            with (
                patch("omargb.apply.load_theme", side_effect=load),
                patch("omargb.apply.load_database", return_value=[entry]),
                patch("omargb.apply.scan", return_value=[target.hardware]),
                patch("omargb.apply.match", return_value=[target]),
                patch("omargb.apply.ENGINES", {"vanguard_k08": Engine()}),
            ):
                report = run(colors=colors, debounce=True, state=state)
            stamp = (state / "last-apply").read_text().strip()
        self.assertEqual(painted, ["#0091ff", "#ff2800"])
        self.assertIn("#ff2800", report.text())
        self.assertEqual(stamp, fingerprint(red, [target], "warmest"))

    def test_a_skipped_palette_is_painted_when_the_file_moves(self):
        blue = Theme(Path("colors.toml"), ((0, 145, 255),), (0, 145, 255))
        red = Theme(Path("colors.toml"), ((255, 40, 0),), (255, 40, 0))
        entry = Entry("usb", "041e:3126", "K08", "vanguard_k08", "gradient", "", "")
        target = Target(entry, Hardware("usb", "041e:3126", "K08"))
        loaded: list[str] = []
        painted: list[str] = []

        def load(_path):
            loaded.append("read")
            return blue if len(loaded) == 1 else red

        class Engine:
            name = "vanguard_k08"

            def apply(self, theme, targets, dry_run):
                painted.append(theme.solid_hex())
                return f"vanguard_k08 {theme.solid_hex()}"

        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            colors = state / "colors.toml"
            colors.write_text("color\n")
            remember(state, blue, [target], "warmest")
            with (
                patch("omargb.apply.load_theme", side_effect=load),
                patch("omargb.apply.load_database", return_value=[entry]),
                patch("omargb.apply.scan", return_value=[target.hardware]),
                patch("omargb.apply.match", return_value=[target]),
                patch("omargb.apply.ENGINES", {"vanguard_k08": Engine()}),
            ):
                report = run(colors=colors, debounce=True, state=state)
            stamp = (state / "last-apply").read_text().strip()
        self.assertEqual(painted, ["#ff2800"])
        self.assertIn("#ff2800", report.text())
        self.assertEqual(stamp, fingerprint(red, [target], "warmest"))

    def test_a_palette_that_keeps_moving_is_not_stamped(self):
        entry = Entry("usb", "041e:3126", "K08", "vanguard_k08", "gradient", "", "")
        target = Target(entry, Hardware("usb", "041e:3126", "K08"))
        reads = {"n": 0}

        def load(_path):
            reads["n"] += 1
            channel = reads["n"] % 255
            colour = (channel, 0, 0)
            return Theme(Path("colors.toml"), (colour,), colour)

        class Engine:
            name = "vanguard_k08"

            def apply(self, theme, targets, dry_run):
                return f"vanguard_k08 {theme.solid_hex()}"

        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            colors = state / "colors.toml"
            colors.write_text("color\n")
            with (
                patch("omargb.apply.load_theme", side_effect=load),
                patch("omargb.apply.load_database", return_value=[entry]),
                patch("omargb.apply.scan", return_value=[target.hardware]),
                patch("omargb.apply.match", return_value=[target]),
                patch("omargb.apply.ENGINES", {"vanguard_k08": Engine()}),
            ):
                report = run(colors=colors, debounce=True, state=state)
            self.assertFalse((state / "last-apply").exists())
        self.assertIn("vanguard_k08", report.text())
        self.assertEqual(reads["n"], PALETTE_PASSES * 2)


class BehaviourTest(unittest.TestCase):
    def _theme(self):
        return Theme(Path("colors.toml"), ((0, 145, 255), (0, 80, 255)), (0, 145, 255))

    def _target(self):
        entry = Entry("usb", "041e:3126", "K08", "vanguard_k08", "gradient", "", "")
        return Target(entry, Hardware("usb", "041e:3126", "K08"))

    def _run(self, policy: Behaviour, calls: list):
        theme = self._theme()
        target = self._target()

        class Engine:
            name = "vanguard_k08"

            def apply(self, theme, targets, dry_run):
                calls.append(targets[0].entry.effect)
                return "vanguard_k08 #0091ff"

        with (
            patch("omargb.apply.load_theme", return_value=theme),
            patch("omargb.apply.load_database", return_value=[target.entry]),
            patch("omargb.apply.scan", return_value=[target.hardware]),
            patch("omargb.apply.match", return_value=[target]),
            patch("omargb.apply.ENGINES", {"vanguard_k08": Engine()}),
        ):
            return run(colors=Path("colors.toml"), behaviour=policy)

    def test_a_disabled_device_is_left_aside(self):
        policy = Behaviour()
        policy.set_device("usb", "041e:3126", enabled=False)
        calls: list[str] = []
        report = self._run(policy, calls)
        self.assertEqual(calls, [])
        self.assertIn("aside K08", report.text())

    def test_solid_override_reaches_the_engine(self):
        policy = Behaviour()
        policy.set_device("usb", "041e:3126", effect="solid")
        calls: list[str] = []
        self._run(policy, calls)
        self.assertEqual(calls, ["solid"])

    def test_painting_off_does_not_open_an_engine(self):
        policy = Behaviour()
        policy.set_enabled(False)
        calls: list[str] = []
        report = self._run(policy, calls)
        self.assertEqual(calls, [])
        self.assertEqual(report.text(), "painting is off")

    def test_describe_keeps_a_disabled_device(self):
        policy = Behaviour()
        policy.set_device("usb", "041e:3126", enabled=False)
        theme = self._theme()
        target = self._target()
        with (
            patch("omargb.apply.load_theme", return_value=theme),
            patch("omargb.apply.load_database", return_value=[target.entry]),
            patch("omargb.apply.scan", return_value=[target.hardware]),
            patch("omargb.apply.match", return_value=[target]),
        ):
            document = describe(colors=Path("colors.toml"), behaviour=policy)
        self.assertTrue(document["ok"])
        self.assertEqual(document["devices"][0]["name"], "K08")
        self.assertFalse(document["devices"][0]["enabled"])
        self.assertTrue(document["devices"][0]["gradient"])
        self.assertTrue(document["devices"][0]["axes"])
        self.assertEqual(document["devices"][0]["direction"], "across")

    def test_config_round_trip_drops_a_default_device(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "behaviour.json"
            policy = Behaviour()
            policy.set_device("hass", "light.zolder", enabled=False)
            policy.set_device("usb", "041e:3126", effect="solid")
            policy.set_device("usb", "041e:3126", effect="default")
            save(policy, path)
            loaded = load(path)
            self.assertFalse(loaded.choice("hass", "light.zolder").enabled)
            self.assertNotIn(("usb", "041e:3126"), loaded.devices)
            self.assertEqual(loaded.strategy, "warmest")
            policy.set_device("openrgb", "G513 RGB MECHANICAL GAMING KEYBOARD", direction="down")
            save(policy, path)
            self.assertEqual(load(path).direction_for("openrgb", "G513 RGB MECHANICAL GAMING KEYBOARD"), "down")
            with self.assertRaises(Exception):
                policy.set_device("openrgb", "G513 RGB MECHANICAL GAMING KEYBOARD", direction="sideways")
            policy.set_strategy("least_blue")
            save(policy, path)
            self.assertEqual(load(path).strategy, "least_blue")
            path.write_text(path.read_text().replace("least_blue", "fixed"))
            with self.assertRaises(Exception):
                load(path)
            path.write_text("{")
            with self.assertRaises(Exception):
                load(path)


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

    def test_warmest_keeps_red_ahead_of_blue(self):
        theme = Theme(
            Path("colors.toml"),
            ((0, 0, 255), (80, 0, 0)),
            (0, 0, 255),
            ((0, 0, 255), (80, 0, 0)),
        )
        self.assertEqual(theme.choose("warmest"), (80, 0, 0))
        self.assertEqual(theme.choose("coolest"), (0, 0, 255))
        self.assertEqual(theme.choose("least_blue"), (80, 0, 0))
        self.assertEqual(theme.choose("brightest"), (0, 0, 255))
        self.assertEqual(theme.choose("nope"), (80, 0, 0))

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
            (6, "G513 RGB MECHANICAL GAMING KEYBOARD", 107),
            (7, "MSI X470 GAMING PLUS MAX (MS-7B79)"),
            (8, "Some Other Lamp"),
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
        self.assertIn("G513 RGB MECHANICAL GAMING KEYBOARD", painted)
        self.assertIn("Corsair Commander Pro", painted)
        self.assertEqual(painted.count("Corsair Vengeance RGB Pro DDR4"), 2)
        self.assertNotIn("Some Other Lamp", painted)

    def test_an_openrgb_keyboard_needs_no_database_row(self):
        openrgb = [
            (0, "Corsair Vengeance RGB Pro DDR4", 10, False),
            (1, "Some Mouse", 11, False),
            (2, "G513 RGB MECHANICAL GAMING KEYBOARD", 107, True),
            (3, "Tiny Keyboard", 1, True),
            (4, "Board LED", 0, False, True),
            (5, "Razer Basilisk V3", 11, False),
            (6, "No Mode", 0, False, False),
        ]
        targets = match(self.entries, [], openrgb)
        names = [target.entry.name for target in targets]
        self.assertIn("G513 RGB MECHANICAL GAMING KEYBOARD", names)
        self.assertIn("Some Mouse", names)
        self.assertNotIn("Tiny Keyboard", names)
        self.assertNotIn("No Mode", names)
        self.assertIn("Razer Basilisk V3", names)
        keyboard = next(target for target in targets if target.entry.name.startswith("G513"))
        self.assertEqual(keyboard.entry.effect, "gradient")
        self.assertEqual(keyboard.openrgb_leds, ((2, 107),))
        self.assertEqual(keyboard.entry.bus, "openrgb")
        self.assertFalse(keyboard.spatial)
        mouse = next(target for target in targets if target.entry.name == "Some Mouse")
        self.assertEqual(mouse.entry.effect, "gradient")
        board = next(target for target in targets if target.entry.name == "Board LED")
        self.assertEqual(board.entry.effect, "solid")
        self.assertEqual(board.openrgb_leds, ())

    def test_an_openlinkhub_usb_id_needs_no_devices_row(self):
        hardware = [Hardware("usb", "1b1c:0c3f", "iCUE LINK System Hub")]
        targets = match(self.entries, hardware, [])
        hub = next(target for target in targets if target.hardware.ident == "1b1c:0c3f")
        self.assertEqual(hub.entry.engine, "openlinkhub")
        self.assertEqual(hub.entry.effect, "solid")
        self.assertEqual(hub.entry.fallback, "")
        self.assertEqual(hub.entry.name, "iCUE LINK System Hub")

    def test_a_per_led_device_on_the_openlinkhub_list_stays_with_openrgb(self):
        hardware = [Hardware("usb", "1b1c:1b55", "K70 RGB MK.2")]
        targets = match(self.entries, hardware, [(0, "Corsair K70 RGB MK.2", 120, True, True)])
        self.assertEqual([target.entry.engine for target in targets], ["openrgb"])
        self.assertEqual(targets[0].entry.effect, "gradient")

    def test_a_static_openlinkhub_device_claims_its_openrgb_controller(self):
        hardware = [Hardware("usb", "1b1c:0c2a", "iCUE COMMANDER Core XT")]
        openrgb = [(1, "Corsair iCUE COMMANDER Core XT", 0, False, True)]
        targets = match(self.entries, hardware, openrgb)
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0].entry.engine, "openlinkhub")
        self.assertEqual(targets[0].entry.fallback, "openrgb")
        self.assertEqual(targets[0].openrgb_devices, ((1, "Corsair iCUE COMMANDER Core XT"),))

    def test_the_commander_row_is_not_duplicated(self):
        hardware = [Hardware("usb", "1b1c:0c10", "Commander PRO")]
        targets = match(self.entries, hardware, [(4, "Corsair Commander Pro", 0, False, True)])
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0].entry.name, "Corsair Commander PRO")

    def test_a_key_matrix_marks_the_keyboard_spatial(self):
        openrgb = [(2, "G513 RGB MECHANICAL GAMING KEYBOARD", 107, True, True, True)]
        targets = match(self.entries, [], openrgb)
        keyboard = next(target for target in targets if target.entry.name.startswith("G513"))
        self.assertTrue(keyboard.spatial)

    def test_a_database_row_claims_a_keyboard_before_the_generic_match(self):
        entries = [Entry("usb", "1532:0099", "Mouse", "openrgb", "solid", "Basilisk", "")]
        openrgb = [(5, "Razer Basilisk V3", 11, True)]
        targets = match(entries, [Hardware("usb", "1532:0099", "Mouse")], openrgb)
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0].entry.effect, "solid")

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


class InstallTest(unittest.TestCase):
    def test_second_run_refreshes_and_drops_stale_copies(self):
        project = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"
            stub = Path(temporary) / "bin"
            log = Path(temporary) / "systemctl.log"
            home.mkdir()
            stub.mkdir()
            (stub / "systemctl").write_text(
                "#!/bin/bash\n"
                'printf "%s\\n" "$*" >> "$OMARGB_SYSTEMCTL_LOG"\n'
                'if [[ $2 == is-enabled ]]; then exit 1; fi\n'
                "exit 0\n"
            )
            (stub / "systemctl").chmod(0o755)
            env = os.environ.copy()
            env["HOME"] = str(home)
            env["PATH"] = f"{stub}:{env.get('PATH', '')}"
            env["OMARGB_SYSTEMCTL_LOG"] = str(log)
            env["OMARGB_INSTALL_UPDATE"] = "0"
            env["OMARGB_INSTALL_DEPS"] = "0"
            env["OMARGB_INSTALL_SHELL"] = "0"

            def install() -> subprocess.CompletedProcess[str]:
                completed = subprocess.run(
                    ["bash", str(project / "install.sh")],
                    cwd=project,
                    env=env,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                return completed

            k08 = home / ".config/omarchy/hooks/theme-set.d/vanguard-k08-rgb"
            k08.parent.mkdir(parents=True)
            k08.write_text("#!/bin/bash\necho paint\n")

            first = install()
            self.assertIn("Installed into this session.", first.stdout)
            parked = home / ".local/state/omargb/parked-hooks/theme-set.d/vanguard-k08-rgb"
            self.assertEqual(parked.read_text(), "#!/bin/bash\necho paint\n")
            self.assertFalse(k08.exists())
            self.assertFalse(k08.with_name("vanguard-k08-rgb.disabled-by-omargb").exists())
            share = home / ".local/share/omargb"
            hooks = home / ".config/omarchy/hooks"
            stale = share / "shims" / "retired-painter"
            stale.write_text("old\n")
            retired_unit = home / ".config/systemd/user/omargb-retired.path"
            retired_unit.write_text("[Path]\n")
            state = home / ".local/state/omargb/install.json"
            recorded = json.loads(state.read_text())
            recorded["installed"].append(str(retired_unit))
            state.write_text(json.dumps(recorded, indent=2) + "\n")

            legacy = hooks / "post-boot.d/vanguard-k08-rgb.disabled-by-omargb"
            legacy.parent.mkdir(parents=True, exist_ok=True)
            legacy.write_text("old\n")

            second = install()
            self.assertIn("Updated hooks, shims, and units from this checkout.", second.stdout)
            self.assertFalse(legacy.exists())
            self.assertEqual(
                (home / ".local/state/omargb/parked-hooks/post-boot.d/vanguard-k08-rgb").read_text(),
                "old\n",
            )

            self.assertFalse(stale.exists())
            self.assertFalse(retired_unit.exists())
            self.assertEqual((hooks / "theme-set.d/omargb").read_text(), (project / "hooks/theme-set.sh").read_text())
            self.assertEqual((share / "shims/omarchy-theme-set-keyboard").read_text(), (project / "shims/omarchy-theme-set-keyboard").read_text())
            self.assertEqual((share / "src").resolve(), project)
            self.assertEqual((home / ".local/bin/omargb").resolve(), (project / "bin/omargb").resolve())
            after = json.loads(state.read_text())
            self.assertEqual(after["disabled_hooks"], [
                "theme-set.d/vanguard-k08-rgb",
                "post-boot.d/vanguard-k08-rgb",
            ])
            self.assertEqual(after["disabled_units"], [])
            self.assertNotIn(str(retired_unit), after["installed"])
            self.assertIn(str(share / "shims/omarchy-theme-set-keyboard"), after["installed"])
            self.assertIn("enable --now omargb-theme.path", log.read_text())
            self.assertEqual(
                (home / ".config/omarchy/plugins/io.github.ekollof.omargb/manifest.json").read_text(),
                (project / "shell/manifest.json").read_text(),
            )

    def test_update_fast_forwards_a_clean_checkout_and_stops_when_diverged(self):
        project = Path(__file__).resolve().parent.parent
        ui = project / "share/omarchy-ui.sh"
        with tempfile.TemporaryDirectory() as temporary:
            origin = Path(temporary) / "origin"
            checkout = Path(temporary) / "checkout"
            relaunch = Path(temporary) / "relaunch"
            marker = Path(temporary) / "relaunched"
            origin.mkdir()
            relaunch.write_text("#!/bin/bash\ngit -C \"$CHECKOUT\" rev-parse HEAD > \"$MARKER\"\n")
            relaunch.chmod(0o755)
            self._git(origin, "init", "-b", "master")
            self._git(origin, "config", "user.email", "test@example.com")
            self._git(origin, "config", "user.name", "Test")
            (origin / "README").write_text("one\n")
            self._git(origin, "add", "README")
            self._git(origin, "commit", "-m", "one")
            self._git(Path(temporary), "clone", str(origin), str(checkout))
            self._git(checkout, "config", "user.email", "test@example.com")
            self._git(checkout, "config", "user.name", "Test")
            (origin / "README").write_text("two\n")
            self._git(origin, "add", "README")
            self._git(origin, "commit", "-m", "two")

            forwarded = self._update(ui, checkout, relaunch, marker)
            self.assertEqual(forwarded.returncode, 0, forwarded.stderr)
            self.assertEqual(marker.read_text().strip(), self._git(origin, "rev-parse", "HEAD").stdout.strip())
            self.assertEqual(self._git(checkout, "rev-parse", "HEAD").stdout, self._git(origin, "rev-parse", "HEAD").stdout)
            self.assertIn("Updated this checkout", forwarded.stdout)

            marker.unlink()
            (checkout / "local").write_text("mine\n")
            self._git(checkout, "add", "local")
            self._git(checkout, "commit", "-m", "local")
            (origin / "README").write_text("three\n")
            self._git(origin, "add", "README")
            self._git(origin, "commit", "-m", "three")
            stayed = self._git(checkout, "rev-parse", "HEAD").stdout
            diverged = self._update(ui, checkout, relaunch, marker)
            self.assertEqual(diverged.returncode, 0, diverged.stderr)
            self.assertFalse(marker.exists())
            self.assertEqual(self._git(checkout, "rev-parse", "HEAD").stdout, stayed)
            self.assertIn("ahead or diverged", diverged.stdout + diverged.stderr)

    def _git(self, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(cwd), *args],
            text=True,
            capture_output=True,
            check=True,
        )

    def _update(self, ui: Path, checkout: Path, relaunch: Path, marker: Path) -> subprocess.CompletedProcess[str]:
        script = f"""
set -euo pipefail
root={checkout}
# shellcheck disable=SC1091
source "{ui}"
omargb_update_checkout "{checkout}" "{relaunch}"
"""
        env = os.environ.copy()
        env["CHECKOUT"] = str(checkout)
        env["MARKER"] = str(marker)
        env.pop("OMARGB_INSTALL_UPDATED", None)
        return subprocess.run(["bash", "-c", script], text=True, capture_output=True, check=False, env=env)


class DepsTest(unittest.TestCase):
    def test_packages_follow_matched_engines_including_fallback(self):
        from omargb.deps import report

        text = report(
            [
                Hardware("usb", "1b1c:0c10", "Corsair Commander PRO"),
                Hardware("usb", "041e:3126", "Sound BlasterX Vanguard K08"),
                Hardware("dmi", "Framework:Laptop 16", "Framework Laptop 16"),
            ],
            [],
        )
        self.assertIn("device\tCorsair Commander PRO", text)
        self.assertIn("device\tSound BlasterX Vanguard K08", text)
        self.assertIn("package\taur\topenlinkhub-bin", text)
        self.assertIn("package\tarch\topenrgb", text)
        self.assertIn("package\tarch\tqmk-hid", text)
        self.assertIn("service\topenlinkhub.service", text)
        self.assertIn("service\topenrgb.service", text)
        self.assertIn("udev\tdefault/udev/framework16-qmk-hid.rules\t/etc/udev/rules.d/50-framework16-qmk-hid.rules", text)
        self.assertNotIn("asusctl", text)
        self.assertEqual(text.count("package\tarch\topenrgb"), 1)

    def test_no_hardware_installs_nothing(self):
        from omargb.deps import report

        self.assertEqual(report([], []), "")


class HassTest(unittest.TestCase):
    def test_scan_reads_lamps_and_drops_a_bad_entity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "config/hass.cfg"
            config.parent.mkdir()
            config.write_text(
                "[auth]\n"
                "server = http://hass.example:8123/\n"
                "token = test-token\n"
                "lamp = light.zolder, light.bad name, switch.other\n"
            )
            found = [item.ident for item in scan(root) if item.bus == "hass"]
        self.assertEqual(found, ["light.zolder", "switch.other"])

    def test_database_matches_every_light_and_leaves_other_entities_dark(self):
        entries = load_database()
        hardware = [
            Hardware("hass", "light.zolder", "light.zolder"),
            Hardware("hass", "light.ledstrip", "light.ledstrip"),
            Hardware("hass", "switch.other", "switch.other"),
        ]
        matched = [target.hardware.ident for target in match(entries, hardware, [])]
        self.assertEqual(matched, ["light.zolder", "light.ledstrip"])

    def test_dry_run_does_not_call_the_api(self):
        targets = match(
            load_database(),
            [Hardware("hass", "light.zolder", "light.zolder")],
            [],
        )
        theme = Theme(Path("colors.toml"), ((0, 145, 255),), (0, 145, 255))

        def explode(*_args, **_kwargs):
            raise AssertionError("dry_run called the API")

        with patch("omargb.engines.homeassistant.urllib.request.urlopen", explode):
            text = HomeAssistant().apply(theme, targets, dry_run=True)
        self.assertEqual(text, "homeassistant dry-run light.zolder #0091ff")

    def test_apply_picks_the_warmest_colour_for_lamps(self):
        targets = match(load_database(), [Hardware("hass", "light.zolder", "light.zolder")], [])
        theme = Theme(
            Path("colors.toml"),
            ((0, 0, 255), (255, 40, 0)),
            (0, 0, 255),
            ((0, 0, 255), (255, 40, 0)),
        )
        warm = _apply(theme, targets, True, Behaviour()).text()
        self.assertIn("light.zolder #ff2800", warm)
        cool = Behaviour()
        cool.set_strategy("coolest")
        self.assertIn("light.zolder #0000ff", _apply(theme, targets, True, cool).text())

    def test_apply_sets_rgb_only_when_the_light_is_on(self):
        targets = match(
            load_database(),
            [
                Hardware("hass", "light.zolder", "light.zolder"),
                Hardware("hass", "light.off", "light.off"),
            ],
            [],
        )
        theme = Theme(Path("colors.toml"), ((0, 145, 255),), (0, 145, 255))
        posted: list[dict] = []

        class Response:
            def __init__(self, payload: str) -> None:
                self.payload = payload

            def read(self) -> bytes:
                return self.payload.encode()

            def __enter__(self):
                return self

            def __exit__(self, *_args) -> bool:
                return False

        def urlopen(request, timeout=0):
            self.assertEqual(timeout, 10)
            self.assertTrue(request.get_header("Authorization", "").startswith("Bearer "))
            if request.get_method() == "GET":
                state = "on" if request.full_url.endswith("light.zolder") else "off"
                return Response(json.dumps({"state": state}))
            posted.append(json.loads(request.data.decode()))
            return Response("")

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "hass.cfg"
            path.write_text("[auth]\nserver=http://hass.example\ntoken=test-token\nlamp=light.zolder, light.off\n")
            path.chmod(0o600)
            with (
                patch("omargb.engines.homeassistant.config_path", return_value=path),
                patch("omargb.engines.homeassistant.urllib.request.urlopen", urlopen),
            ):
                text = HomeAssistant().apply(theme, targets, dry_run=False)
        self.assertEqual(posted, [{"entity_id": "light.zolder", "rgb_color": [0, 145, 255]}])
        self.assertIn("light.zolder #0091ff", text)
        self.assertIn("light.off off", text)
        self.assertNotIn("test-token", text or "")

    def test_loose_config_is_rejected_without_a_request(self):
        targets = match(load_database(), [Hardware("hass", "light.zolder", "light.zolder")], [])
        theme = Theme(Path("colors.toml"), ((0, 145, 255),), (0, 145, 255))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "hass.cfg"
            path.write_text("[auth]\nserver=http://hass.example\ntoken=test-token\nlamp=light.zolder\n")
            path.chmod(0o644)

            def explode(*_args, **_kwargs):
                raise AssertionError("a loose config called the API")

            with (
                patch("omargb.engines.homeassistant.config_path", return_value=path),
                patch("omargb.engines.homeassistant.urllib.request.urlopen", explode),
            ):
                text = HomeAssistant().apply(theme, targets, dry_run=False)
        self.assertIn("rejected", text or "")
        self.assertNotIn("test-token", text or "")


def _orgb_string(text: str) -> bytes:
    raw = text.encode() + b"\x00"
    return struct.pack("<H", len(raw)) + raw


def _orgb_device(name: str, leds: int, flags: int, bright_max: int, matrix: tuple[int, ...] | None = None) -> bytes:
    """A protocol-4 controller blob with one mode, a matrix zone, and a segment.

    `matrix` is the row-major LED indexes. The width is half the length when the
    length is even, otherwise one row. An empty matrix means the zone has none.
    """
    body = struct.pack("<i", 5)
    for text in (name, "Razer", "keyboard", "1", "", "hid"):
        body += _orgb_string(text)
    body += struct.pack("<Hi", 1, 0)
    body += _orgb_string("Direct")
    body += struct.pack("<i11IH", 0, flags, 0, 0, 0, bright_max, 0, 0, 0, 0, 0, 1, 0)
    body += struct.pack("<H", 1)
    body += _orgb_string("Keyboard")
    body += struct.pack("<iIII", 2, 1, leds, leds)
    if matrix is None:
        matrix = (0,)
    if matrix:
        width = max(len(matrix) // 2, 1)
        height = len(matrix) // width
        body += struct.pack("<HII", len(matrix), height, width)
        body += struct.pack("<" + "I" * len(matrix), *matrix)
    else:
        body += struct.pack("<H", 0)
    body += struct.pack("<H", 1)
    body += _orgb_string("Main")
    body += struct.pack("<iII", 1, 0, leds)
    body += struct.pack("<H", leds)
    for index in range(leds):
        body += _orgb_string(f"LED {index}") + struct.pack("<I", index)
    body += struct.pack("<H", 0)
    return struct.pack("<I", 4 + len(body)) + body


def _orgb_packet(dev: int, pkt: int, payload: bytes) -> bytes:
    return struct.pack("<4sIII", b"ORGB", dev, pkt, len(payload)) + payload


class _Buf:
    def __init__(self, incoming: bytes = b""):
        self.incoming = incoming
        self.at = 0
        self.sent = bytearray()
        self.closed = False

    def sendall(self, data: bytes) -> None:
        self.sent += data

    def recv(self, size: int) -> bytes:
        chunk = self.incoming[self.at:self.at + size]
        if not chunk:
            raise ConnectionError("closed")
        self.at += len(chunk)
        return chunk

    def close(self) -> None:
        self.closed = True


class OpenRgbTest(unittest.TestCase):
    def _theme(self) -> Theme:
        return Theme(Path("colors.toml"), ((255, 0, 255), (255, 0, 0)), (255, 0, 255))

    def _target(self, leds: int, effect: str = "gradient") -> Target:
        entry = Entry("usb", "1532:024e", "Razer BlackWidow V3", "openrgb", effect, "Blackwidow V3", "")
        counted = ((5, leds),) if leds > 1 else ()
        return Target(entry, Hardware("usb", "1532:024e", "Razer BlackWidow V3"), ((5, "Razer Blackwidow V3"),), counted)

    def test_description_keeps_a_matrix_zone_and_the_led_count(self):
        controller = parse_controller(_orgb_device("Razer Blackwidow V3", 2, 0x30, 255), 5)
        self.assertEqual(controller.name, "Razer Blackwidow V3")
        self.assertEqual(controller.leds, 2)
        self.assertEqual(controller.gradient_count, 2)
        mode = controller.per_led_mode
        self.assertIsNotNone(mode)
        self.assertEqual(mode.name, "Direct")
        self.assertEqual(mode.flags, 0x30)
        self.assertEqual(mode.brightness_max, 255)
        self.assertEqual(parse_controller(_orgb_device("Board", 1, 0x20, 0), 7).gradient_count, 0)

    def test_packets_set_full_brightness_and_padded_colours(self):
        mode = parse_controller(_orgb_device("Razer Blackwidow V3", 2, 0x30, 255), 5).per_led_mode
        packet = pack_update_mode(mode, mode.brightness_max)
        size, mode_index = struct.unpack_from("<Ii", packet)
        self.assertEqual(size, len(packet))
        self.assertEqual(mode_index, 0)
        name_len = struct.unpack_from("<H", packet, 8)[0]
        fields = struct.unpack_from("<i11IH", packet, 10 + name_len)
        self.assertEqual(fields[9], 255)
        self.assertEqual(pack_leds([(1, 2, 3), (4, 5, 6)]), struct.pack("<IHBBBxBBBx", 14, 2, 1, 2, 3, 4, 5, 6))

    def test_list_uses_the_server_and_retries_a_missed_wakeup(self):
        blob = _orgb_device("Razer Blackwidow V3", 132, 0x30, 255)
        incoming = _orgb_packet(0, 0, struct.pack("<I", 1)) + _orgb_packet(5, 1, blob)
        calls = {"n": 0}

        def opener():
            calls["n"] += 1
            if calls["n"] == 1:
                raise TimeoutError("wakeup")
            return Link(_Buf(incoming))

        found = list_devices(opener)
        self.assertEqual(found, [(5, "Razer Blackwidow V3", 132, True, True, True)])
        self.assertEqual(calls["n"], 2)

        def refuse():
            raise ConnectionRefusedError()

        self.assertEqual(list_devices(refuse), [])

    def test_a_short_description_does_not_raise(self):
        incoming = _orgb_packet(0, 0, struct.pack("<I", 1)) + _orgb_packet(0, 1, b"\x04\x00\x00\x00")
        self.assertEqual(list_devices(lambda: Link(_Buf(incoming))), [])

    def test_dry_run_does_not_open_the_server(self):
        def explode(*_args, **_kwargs):
            raise AssertionError("dry-run opened the server")

        with patch("omargb.engines.openrgb.session", explode):
            text = OpenRgb().apply(self._theme(), [self._target(132)], dry_run=True)
        self.assertEqual(text, "openrgb dry-run 5:Razer Blackwidow V3 gradient")

    def test_apply_spreads_stops_across_the_live_led_count(self):
        controller = parse_controller(_orgb_device("Razer Blackwidow V3", 3, 0x30, 255), 5)
        recorded: list[tuple[int, list[tuple[int, int, int]]]] = []

        class Recorder:
            def paint(self, device, colours):
                recorded.append((device.index, colours))

            def close(self):
                pass

        with patch("omargb.engines.openrgb.session", return_value=(Recorder(), [controller])):
            text = OpenRgb().apply(self._theme(), [self._target(3)], dry_run=False)
        self.assertEqual(text, "openrgb 5:Razer Blackwidow V3 gradient")
        self.assertEqual(recorded[0][0], 5)
        self.assertEqual(recorded[0][1], [(255, 0, 255), (255, 0, 128), (255, 0, 0)])

    def test_a_keyboard_gradient_runs_left_to_right(self):
        # LED list order is row by row, which paints top to bottom.
        # The matrix puts 0 and 2 in the left column and 1 and 3 in the right.
        blob = _orgb_device("Razer Blackwidow V3", 4, 0x30, 255, matrix=(0, 1, 2, 3))
        controller = parse_controller(blob, 5)
        self.assertEqual(controller.places, ((0, 0), (1, 0), (0, 1), (1, 1)))
        self.assertEqual(
            _colours(self._theme(), "gradient", controller),
            [(255, 0, 255), (255, 0, 0), (255, 0, 255), (255, 0, 0)],
        )
        self.assertEqual(
            _colours(self._theme(), "gradient", controller, "down"),
            [(255, 0, 255), (255, 0, 255), (255, 0, 0), (255, 0, 0)],
        )

    def test_vanguard_down_runs_from_the_top_of_each_column(self):
        stops = [(255, 0, 255), (255, 0, 0)]
        across = dict(led_colours(stops, "across"))
        down = dict(led_colours(stops, "down"))
        ordered = [led for zone in ZONES for led in zone]
        self.assertEqual(across[ordered[0]], (255, 0, 255))
        self.assertEqual(across[ordered[-1]], (255, 0, 0))
        self.assertEqual(down[ZONES[0][0]], (255, 0, 255))
        self.assertEqual(down[ZONES[0][-1]], (255, 0, 0))
        self.assertEqual(down[ZONES[1][0]], (255, 0, 255))
        self.assertNotEqual(down[ZONES[0][len(ZONES[0]) // 2]], across[ZONES[0][len(ZONES[0]) // 2]])

    def test_a_mode_without_brightness_uses_custom_mode(self):
        mode = Mode(0, "Direct", 0, 0x20, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, ())
        sock = _Buf()
        Link(sock).paint(Controller(1, "DRAM", 2, (mode,)), [(8, 0, 0), (0, 8, 0)])
        ids = []
        offset = 0
        while offset + 16 <= len(sock.sent):
            _magic, _dev, pkt, size = struct.unpack_from("<4sIII", sock.sent, offset)
            ids.append(pkt)
            offset += 16 + size
        self.assertEqual(ids, [1100, 1050])

    def test_a_controller_with_no_leds_uses_its_static_mode(self):
        mode = Mode(5, "Static", 0, 0x250, 0, 0, 0, 100, 1, 1, 0, 0, 0, 2, ((0, 0, 0),))
        controller = Controller(4, "Corsair Commander Pro", 0, (mode,))
        sock = _Buf()
        self.assertTrue(Link(sock).paint_static(controller, (1, 2, 3)))
        _magic, dev, pkt, size = struct.unpack_from("<4sIII", sock.sent)
        self.assertEqual((dev, pkt), (4, 1101))
        body = sock.sent[16:16 + size]
        self.assertIn(struct.pack("<BBBx", 1, 2, 3), body)
        name_len = struct.unpack_from("<H", body, 8)[0]
        self.assertEqual(struct.unpack_from("<i11IH", body, 10 + name_len)[9], 100)

        entry = Entry("usb", "1b1c:0c10", "Corsair Commander PRO", "openrgb", "solid", "Commander Pro", "")
        target = Target(entry, Hardware("usb", "1b1c:0c10", "Commander"), ((4, "Corsair Commander Pro"),))

        class Recorder:
            def __init__(self):
                self.static = []

            def paint(self, *_args):
                raise AssertionError("a controller with no LEDs took per-LED colours")

            def paint_static(self, device, colour):
                self.static.append((device.index, colour))
                return True

            def close(self):
                pass

        recorder = Recorder()
        with patch("omargb.engines.openrgb.session", return_value=(recorder, [controller])):
            text = OpenRgb().apply(self._theme(), [target], dry_run=False)
        self.assertEqual(text, "openrgb 4:Corsair Commander Pro #ff00ff")
        self.assertEqual(recorder.static, [(4, (255, 0, 255))])

    def test_server_down_is_not_ready(self):
        with patch("omargb.engines.openrgb.session", return_value=None):
            text = OpenRgb().apply(self._theme(), [self._target(2)], dry_run=False)
        self.assertEqual(text, "openrgb: not ready")

    def test_greet_asks_for_protocol_4(self):
        sock = _Buf(_orgb_packet(0, 40, struct.pack("<I", 6)))
        greet(Link(sock))
        self.assertIn(struct.pack("<I", 4), bytes(sock.sent))
        self.assertIn(b"omargb\x00", bytes(sock.sent))
        self.assertTrue(sock.sent.startswith(b"ORGB"))


if __name__ == "__main__":
    unittest.main()

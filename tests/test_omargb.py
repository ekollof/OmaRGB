#!/usr/bin/env python3
"""Matcher and palette tests. No hardware."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from omargb.apply import Report, run
from omargb.console import present_lines, status_mark
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

            first = install()
            self.assertIn("Installed into this session.", first.stdout)
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

            second = install()
            self.assertIn("Updated hooks, shims, and units from this checkout.", second.stdout)

            self.assertFalse(stale.exists())
            self.assertFalse(retired_unit.exists())
            self.assertEqual((hooks / "theme-set.d/omargb").read_text(), (project / "hooks/theme-set.sh").read_text())
            self.assertEqual((share / "shims/omarchy-theme-set-keyboard").read_text(), (project / "shims/omarchy-theme-set-keyboard").read_text())
            self.assertEqual((share / "src").resolve(), project)
            self.assertEqual((home / ".local/bin/omargb").resolve(), (project / "bin/omargb").resolve())
            after = json.loads(state.read_text())
            self.assertEqual(after["disabled_hooks"], [])
            self.assertEqual(after["disabled_units"], [])
            self.assertNotIn(str(retired_unit), after["installed"])
            self.assertIn(str(share / "shims/omarchy-theme-set-keyboard"), after["installed"])
            self.assertIn("enable --now omargb-theme.path", log.read_text())

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


if __name__ == "__main__":
    unittest.main()

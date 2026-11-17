"""Command line for OmaRGB."""

import argparse
import fcntl
import sys
from pathlib import Path

from omargb.apply import run
from omargb.console import show_report

LOCK = Path.home() / ".local/state/omargb/apply.lock"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="omargb", description="Apply the Omarchy theme to RGB hardware")
    parser.add_argument("command", choices=("apply", "plan"), nargs="?", default="apply")
    parser.add_argument("--colors", type=Path, help="colors.toml to read instead of the active theme")
    parser.add_argument("--database", type=Path, help="device database to use instead of the shipped one")
    parser.add_argument(
        "--debounce",
        action="store_true",
        help="skip when this palette and these devices were just painted",
    )
    args = parser.parse_args(argv)

    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        report = run(
            colors=args.colors,
            database=args.database,
            dry_run=args.command == "plan",
            debounce=args.debounce,
        )
    show_report(report, args.command)
    return 75 if report.not_ready else 0


if __name__ == "__main__":
    sys.exit(main())

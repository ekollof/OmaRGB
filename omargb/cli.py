"""Command line for OmaRGB."""

import argparse
import fcntl
import json
import sys
from pathlib import Path

from omargb.apply import describe, run
from omargb.behaviour import BehaviourError, load, parse_bool, save
from omargb.console import show_report

LOCK = Path.home() / ".local/state/omargb/apply.lock"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="omargb", description="Apply the Omarchy theme to RGB hardware")
    parser.add_argument("command", choices=("apply", "plan", "config"), nargs="?", default="apply")
    parser.add_argument("config_args", nargs="*", help=argparse.SUPPRESS)
    parser.add_argument("--colors", type=Path, help="colors.toml to read instead of the active theme")
    parser.add_argument("--database", type=Path, help="device database to use instead of the shipped one")
    parser.add_argument("--json", action="store_true", help="print the plan as JSON")
    parser.add_argument(
        "--debounce",
        action="store_true",
        help="skip when this palette and these devices were just painted",
    )
    parser.add_argument("--config", type=Path, help="behaviour file to read instead of the default")
    args = parser.parse_args(argv)

    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        if args.command == "config":
            return _config(args.config_args, args.config)
        if args.json:
            if args.command != "plan":
                print("omargb: --json is for plan", file=sys.stderr)
                return 2
            print(json.dumps(describe(
                colors=args.colors,
                database=args.database,
                behaviour_path=args.config,
                read_behaviour=True,
            )))
            return 0
        report = run(
            colors=args.colors,
            database=args.database,
            dry_run=args.command == "plan",
            debounce=args.debounce,
            behaviour_path=args.config,
            read_behaviour=True,
        )
    show_report(report, args.command)
    return 75 if report.not_ready else 0


def _config(words: list[str], path: Path | None) -> int:
    try:
        behaviour = load(path)
        if not words:
            print(json.dumps(behaviour.document()))
            return 0
        if words[0] == "enabled" and len(words) == 2:
            behaviour.set_enabled(parse_bool(words[1]))
        elif words[0] == "strategy" and len(words) == 2:
            behaviour.set_strategy(words[1])
        elif words[0] == "device" and len(words) == 5 and words[3] in ("enabled", "effect", "direction"):
            enabled = parse_bool(words[4]) if words[3] == "enabled" else None
            effect = words[4] if words[3] == "effect" else None
            direction = words[4] if words[3] == "direction" else None
            behaviour.set_device(words[1], words[2], enabled=enabled, effect=effect, direction=direction)
        else:
            print("omargb: config enabled true|false", file=sys.stderr)
            print("omargb: config strategy warmest|least_blue|most_saturated|coolest|brightest", file=sys.stderr)
            print("omargb: config device <bus> <id> enabled true|false", file=sys.stderr)
            print("omargb: config device <bus> <id> effect solid|gradient|default", file=sys.stderr)
            print("omargb: config device <bus> <id> direction across|down|default", file=sys.stderr)
            return 2
        save(behaviour, path)
    except BehaviourError as exc:
        print(f"omargb: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(behaviour.document()))
    return 0


if __name__ == "__main__":
    sys.exit(main())

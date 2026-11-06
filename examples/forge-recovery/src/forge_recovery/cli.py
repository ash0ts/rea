from __future__ import annotations

import argparse
import json
from pathlib import Path

from .benchmark import prepare
from .checker import grade


def main() -> None:
    parser = argparse.ArgumentParser(description="REA animation recovery experiment")
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("prepare")
    setup.add_argument("--root", type=Path, required=True)
    setup.add_argument("--source", type=Path)
    check = commands.add_parser("check")
    check.add_argument("--output", type=Path, required=True)
    check.add_argument("--expected", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        print(json.dumps(prepare(args.root, args.source), indent=2))
    else:
        result = grade(args.output, args.expected)
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()

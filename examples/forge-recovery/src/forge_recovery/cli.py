from __future__ import annotations

import argparse
import asyncio
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
    for name in ("qualify", "run"):
        command = commands.add_parser(name)
        command.add_argument("--root", type=Path, required=True)
        command.add_argument("--prepared", type=Path, required=True)
        command.add_argument("--entity", required=True)
        command.add_argument("--ledger", type=Path, required=True, help="Shared durable ledger across all campaigns; never reset it to retry")
        if name == "qualify":
            command.add_argument("--run-scored", action="store_true", help="Continue into scored attempts after qualification, retaining images across both phases")
    summary = commands.add_parser("summarize")
    summary.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        print(json.dumps(prepare(args.root, args.source), indent=2))
    elif args.command == "check":
        result = grade(args.output, args.expected)
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result["passed"] else 1)
    elif args.command == "summarize":
        from .experiment import summarize
        print(json.dumps(summarize(args.root), indent=2))
    else:
        from .experiment import execute
        phase = "all" if args.command == "qualify" and args.run_scored else "qualification" if args.command == "qualify" else "scored"
        result = asyncio.run(execute(args.root.resolve(), args.prepared.resolve(), args.entity,
            phase, args.ledger.resolve()))
        print(json.dumps({key: value for key, value in result.items() if key != "attempts"}, indent=2))


if __name__ == "__main__":
    main()

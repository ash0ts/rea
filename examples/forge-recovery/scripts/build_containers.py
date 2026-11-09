"""Retain each built image until the optional campaign command has completed."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import uuid4

EXAMPLE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXAMPLE / "src"))

from forge_recovery.common import REA_REVISION
from forge_recovery.sandbox import Sandbox


def build_and_run(example: Path, command: list[str]) -> None:
    checkout = subprocess.check_output(["git", "-C", str(example), "rev-parse", "--show-toplevel"], text=True).strip()
    owner = "build-" + uuid4().hex
    receipts = example / ".local" / "build-retention" / owner
    with ExitStack() as retained:
        with tempfile.TemporaryDirectory(prefix="rea-recovery-build-") as temporary:
            context = Path(temporary)
            subprocess.run(["git", "-C", checkout, "archive", "--format=tar", "-o", str(context / "rea-source.tar"), REA_REVISION], check=True)
            for role in ("base", "rea", "checker"):
                image = f"rea-forge-recovery-{role}:v1"
                source = context if role == "rea" else example / "containers"
                subprocess.run(["docker", "build", "-t", image, "-f", str(example / "containers" / f"Dockerfile.{role}"), str(source)], check=True)
                box = Sandbox(receipts / role, example / "containers", image=image, owner=owner + "-" + role)
                retained.callback(box.close)
                box.start()
        if command:
            subprocess.run(command, check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Optional command after --; images remain referenced while it runs")
    arguments = parser.parse_args().command
    if arguments[:1] == ["--"]:
        arguments = arguments[1:]
    build_and_run(EXAMPLE, arguments)

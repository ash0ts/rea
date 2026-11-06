from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

REA_REVISION = "c92cbcaf281bea28e16146c3555d58a2d62edf03"
PISKEL_REVISION = "745caa20ebebbe3991247064ccc5b51ee9a5490d"
FAMILIES = ("basic", "opacity", "non_square", "chunks", "hidden", "legacy")
BASE_IMAGE = "rea-forge-recovery-base:v1"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def inventory(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): digest(p) for p in sorted(root.rglob("*")) if p.is_file()}


def verify_inventory(root: Path, expected: dict[str, str]) -> None:
    if inventory(root) != expected:
        raise ValueError(f"Frozen inputs changed: {root}")

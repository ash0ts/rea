from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .common import BASE_IMAGE, FAMILIES, PISKEL_REVISION, REA_REVISION, digest, inventory, read_json, verify_inventory, write_json
from .oracle import generate

PACKAGE = Path(__file__).resolve().parents[2]


def stage_bundle(build: Path, target: Path) -> dict:
    bundles = sorted((build / "js").glob("piskel-packaged-min*.js"))
    if len(bundles) != 1:
        raise ValueError(f"Expected one minified bundle, found {len(bundles)}")
    target.mkdir(parents=True, exist_ok=False)
    bundle = bundles[0]
    shutil.copy2(bundle, target / bundle.name)
    notices = {"source": str(bundle.relative_to(build)), "sha256": digest(bundle), "withheld": ["unminified bundles", "source maps", "upstream source", "reference renderer", "held-out cases"], "bytes_modified": False}
    write_json(target / "INPUTS.json", notices)
    return notices


def prepare(root: Path, source: Path | None = None) -> dict:
    root = root.resolve()
    manifest = root / "prepared.json"
    if manifest.exists():
        existing = read_json(manifest)
        verify_inventory(root / "inputs", existing["inputs"])
        verify_inventory(root / "oracle", existing["oracle"])
        if existing["generator_sha256"] != digest(PACKAGE / "scripts/fixtures.js"):
            raise ValueError("Fixture generator changed; create a new preparation")
        return existing
    if root.exists() and any(root.iterdir()):
        raise ValueError("Preparation directory is nonempty without a completed manifest; use a fresh directory")
    root.mkdir(parents=True, exist_ok=True)
    source = source.resolve() if source else root / "piskel-source"
    if not source.exists():
        subprocess.run(["git", "clone", "--no-checkout", "https://github.com/piskelapp/piskel.git", str(source)], check=True)
        subprocess.run(["git", "-C", str(source), "checkout", "--detach", PISKEL_REVISION], check=True)
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if revision != PISKEL_REVISION or subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"], text=True).strip():
        raise ValueError("Piskel source must match the clean pinned revision")
    subprocess.run(["docker", "build", "-t", BASE_IMAGE, "-f", str(PACKAGE / "containers/Dockerfile.base"), str(PACKAGE / "containers")], check=True)
    subprocess.run(["docker", "run", "--rm", "--cpus", "2", "--memory", "4g", "--mount", f"type=bind,src={source},dst=/piskel", "-w", "/piskel", BASE_IMAGE, "sh", "-c", "npm ci --ignore-scripts && npm run build"], check=True)
    target = root / "inputs" / "bundle"
    notice = stage_bundle(source / "dest/prod", target)
    for name in ("LICENSE", "NOTICE"):
        if (source / name).exists():
            shutil.copy2(source / name, target / name)
    reference = generate(source / "dest/prod", root / "oracle", PACKAGE / "scripts/fixtures.js")
    for family in (*FAMILIES, "qualification"):
        destination = root / "inputs" / family
        destination.mkdir(parents=True)
        shutil.copy2(root / "oracle" / family / "visible/animation.piskel", destination / "animation.piskel")
    result = {
        "schema_version": 1, "rea_revision": REA_REVISION, "piskel_revision": revision,
        "base_image_id": subprocess.check_output(["docker", "image", "inspect", BASE_IMAGE, "--format", "{{.Id}}"], text=True).strip(),
        "bundle": notice, "browser_version": reference["browser_version"],
        "inputs": inventory(root / "inputs"), "oracle": inventory(root / "oracle"),
        "generator_sha256": digest(PACKAGE / "scripts/fixtures.js"),
    }
    write_json(manifest, result)
    return result

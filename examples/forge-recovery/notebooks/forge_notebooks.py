"""Read back the native notebook source committed by Forge after editor Save.

Create/open/edit/save through the signed-in Forge notebook UI. Launching a
runtime requires that browser session; an API key alone cannot do it. The
artifact below is the native notebook's committed source, not the staging
source artifact used to populate the editor.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import wandb

from forge_recovery.common import write_json
from forge_recovery.telemetry import credentials, ensure_private_project


def readback(entity: str, notebook_id: str, source: Path, destination: Path) -> dict:
    credentials()
    ensure_private_project(entity)
    api = wandb.Api(timeout=60)
    notebook = api._service_api.execute_graphql(
        'query($id:ID!){notebook(id:$id){id name currentVersion{artifactTypeName artifactCollectionName versionIndex sourceFileName}}}',
        {"id": notebook_id},
    )["notebook"]
    if not notebook or not notebook.get("currentVersion"):
        raise RuntimeError("Notebook has no committed source version")
    version = notebook["currentVersion"]
    reference = f"{entity}/rea-showcase/{version['artifactCollectionName']}:v{version['versionIndex']}"
    artifact = api.artifact(reference)
    downloaded = Path(artifact.get_path(version["sourceFileName"]).download(root=str(destination / "source")))
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    actual = hashlib.sha256(downloaded.read_bytes()).hexdigest()
    receipt = {"notebook_id": notebook_id, "name": notebook["name"], "artifact": reference,
               "artifact_digest": artifact.digest, "source_sha256": actual,
               "expected_sha256": expected, "exact_source_match": expected == actual}
    write_json(destination / "readback.json", receipt)
    if expected != actual:
        raise ValueError("Saved source differs; inspect the downloaded source before declaring publication complete")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--notebook-id", required=True)
    parser.add_argument("--entity", default="wandb")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(readback(args.entity, args.notebook_id, args.source, args.output), indent=2))

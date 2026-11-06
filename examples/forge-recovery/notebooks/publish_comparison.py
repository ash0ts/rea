"""Freeze the complete comparison and pin both checked-in notebook sources."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

import wandb

from forge_recovery.common import read_json, write_json
from forge_recovery.experiment import summarize
from forge_recovery.telemetry import credentials


def publish(root: Path, ledger: Path, prior_roots: list[Path]) -> dict:
    sources = [Path(__file__).parent / name for name in ("recover_animation.py", "compare_recovery.py")]
    if any('comparison_ref = "UNPUBLISHED"' not in source.read_text() for source in sources):
        raise ValueError("Notebooks already pinned; do not create another comparison or silently replace source")
    experiment = read_json(root / "experiment.json")
    summary = summarize(root)
    if summary["recorded_scored"] != 24:
        raise ValueError("Publish only the complete frozen comparison; missing attempts are not zeros")
    if any(r.get("upload_status") != "complete" for r in summary["attempts"]):
        raise ValueError("Retry failed artifact uploads before publishing; do not rerun agents")
    destination = root / "comparison"
    destination.mkdir(exist_ok=True)
    value = {"summary": summary, "inputs": read_json(root / "inputs-publication.json"),
        "qualification": read_json(root / "qualification.json"), "ledger": read_json(ledger),
        "experiment": experiment, "qualification_attempts": [
            read_json(root / "attempts" / attempt["attempt_id"] / "result.json")
            for attempt in experiment["qualification"]
        ], "prior_qualification": [
            read_json(result) for prior in prior_roots for result in sorted((prior / "attempts").glob("*/result.json"))
        ], "cleanup_reconciliations": [
            read_json(receipt) for prior in prior_roots
            for receipt in sorted((prior / "attempts").glob("*/cleanup-reconciliation.json"))
        ]}
    readbacks = root / "artifact-readback.json"
    value["artifact_readbacks"] = read_json(readbacks) if readbacks.exists() else []
    # Count returned tool calls from recorded events; absent logs stay unknown.
    # This describes treatment use without changing any attempt result or score.
    value["tool_usage"] = {}
    for row in summary["attempts"]:
        events = root / "attempts" / row["attempt_id"] / "events.json"
        if events.exists():
            counts = Counter(event["tool"] for event in read_json(events) if event["kind"] == "tool")
            value["tool_usage"][row["attempt_id"]] = {
                "returned_calls": sum(counts.values()),
                "rea_returned_calls": sum(count for name, count in counts.items() if name != "execute"),
                "by_tool": dict(counts),
            }
        else:
            value["tool_usage"][row["attempt_id"]] = None
    write_json(destination / "comparison.json", value)
    credentials()
    entity = experiment["entity"]
    with wandb.init(entity=entity, project="rea-showcase", job_type="comparison", dir=str(root),
                    settings=wandb.Settings(disable_git=True, disable_code=True, console="off")) as run:
        artifact = wandb.Artifact(experiment["experiment_id"] + "-comparison", type="recovery-comparison")
        artifact.add_file(str(destination / "comparison.json"), name="comparison.json")
        logged = run.log_artifact(artifact).wait()
        reference = f"{entity}/rea-showcase/{logged.name}"
        receipt = {"artifact": reference, "digest": logged.digest, "run_url": run.url}
    # Preserve the source of the exact immutable artifact consumed by each notebook.
    for source in sources:
        text = source.read_text()
        source.write_text(text.replace('comparison_ref = "UNPUBLISHED"', f'comparison_ref = "{reference}"'))
    write_json(root / "comparison-publication.json", receipt)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--prior-root", type=Path, action="append", default=[])
    args = parser.parse_args()
    print(json.dumps(publish(args.root, args.ledger, args.prior_root), indent=2))

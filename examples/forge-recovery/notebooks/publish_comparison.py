"""Freeze the complete comparison and pin both checked-in notebook sources."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import json
from pathlib import Path

import wandb

from forge_recovery.common import digest, read_json, write_json
from forge_recovery.experiment import summarize
from forge_recovery.telemetry import credentials
from recheck_preview import source_hashes


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
    if any(r.get("cleanup_status") != "complete" for r in summary["attempts"]):
        raise ValueError("Reconcile owned cleanup receipts before final publication")
    original_summary = copy.deepcopy(summary)
    recheck = None
    checker = Path(__file__).resolve().parents[1] / "containers/preview_check.py"
    if experiment["code"]["containers/preview_check.py"] != digest(checker):
        folder = root / "preview-recheck"
        if not (folder / "publication.json").exists():
            raise ValueError("The checker changed: complete and publish a uniform recorded-output recheck first")
        recheck = read_json(folder / "summary.json")
        manifest = recheck["manifest"]
        expected_ids = {r["attempt_id"] for r in summary["attempts"]}
        if not recheck["complete"] or set(recheck["attempts"]) != expected_ids or manifest["configuration_sha256"] != experiment["configuration_sha256"]:
            raise ValueError("Uniform recheck does not cover this complete frozen campaign")
        if any(manifest.get(key) != value for key, value in source_hashes().items()):
            raise ValueError("Uniform recheck source changed after verification")
        if any(manifest["original_result_sha256"][aid] != digest(root / "attempts" / aid / "result.json") for aid in expected_ids):
            raise ValueError("An original attempt changed after the uniform recheck")
        for row in summary["attempts"]:
            corrected = recheck["attempts"][row["attempt_id"]]["checker"]
            if corrected is not None:
                row["checker"] = corrected
        for arm in summary["arms"]:
            summary["arms"][arm]["passed"] = sum(bool(r.get("checker", {}).get("passed")) for r in summary["attempts"] if r["arm"] == arm)
        summary["score_basis"] = "Uniform corrected preview checks; original agent outcomes, pixels, regressions and resource measurements retained"
        recheck["publication"] = read_json(folder / "publication.json")
    else:
        summary["score_basis"] = "Original independent checker"
    destination = root / "comparison"
    destination.mkdir(exist_ok=True)
    value = {"summary": summary, "original_summary": original_summary, "preview_recheck": recheck, "inputs": read_json(root / "inputs-publication.json"),
        "qualification": read_json(root / "qualification.json"), "ledger": read_json(ledger),
        "experiment": experiment, "qualification_attempts": [
            read_json(root / "attempts" / attempt["attempt_id"] / "result.json")
            for attempt in experiment["qualification"]
        ], "prior_qualification": [
            read_json(result) for prior in prior_roots for result in sorted((prior / "attempts").glob("*/result.json"))
        ], "cleanup_reconciliations": [
            read_json(receipt) for prior in [root, *prior_roots]
            for receipt in sorted((prior / "attempts").glob("*/cleanup-reconciliation.json"))
        ]}
    source_receipt = root / "controller-publication.json"
    value["frozen_controller_source"] = read_json(source_receipt) if source_receipt.exists() else None
    if value["frozen_controller_source"] is not None and (root / "controller-readback.json").exists():
        value["frozen_controller_source"]["readback"] = read_json(root / "controller-readback.json")
    value["infrastructure_events"] = [read_json(path) for path in sorted((root / "infrastructure-events").glob("*/event.json"))]
    readbacks = root / "artifact-readback.json"
    value["artifact_readbacks"] = read_json(readbacks) if readbacks.exists() else []
    final_readbacks = root / "artifact-readback-final.json"
    value["scored_artifact_readbacks"] = read_json(final_readbacks) if final_readbacks.exists() else []
    trace_joins = root / "lens-integrity-final.json"
    value["trace_join_verification"] = read_json(trace_joins) if trace_joins.exists() else None
    summary_repair = root / "run-summary-repair.json"
    value["native_run_summary_repair"] = read_json(summary_repair) if summary_repair.exists() else None
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
        if (root / "infrastructure-events").exists():
            artifact.add_dir(str(root / "infrastructure-events"), name="infrastructure-events")
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

"""Uniform recorded-output correction; never starts or replaces an agent attempt."""
from __future__ import annotations

import argparse
import copy
from contextlib import ExitStack
import json
from pathlib import Path
import shutil
import traceback

from forge_recovery.common import digest, inventory, read_json, write_json
from forge_recovery.judge import copy_regular_tree, passed_all_checks
from forge_recovery.sandbox import Sandbox

PACKAGE = Path(__file__).resolve().parents[1]
CHECKER = PACKAGE / "containers/preview_check.py"


def source_hashes() -> dict:
    return {"corrected_checker_sha256": digest(CHECKER),
        "recheck_source_sha256": digest(Path(__file__)),
        "scoring_source_sha256": digest(PACKAGE / "src/forge_recovery/judge.py")}


def campaign(root: Path) -> tuple[dict, list[dict], dict]:
    experiment = read_json(root / "experiment.json")
    if len(experiment["attempts"]) != 24:
        raise ValueError("Uniform correction requires the complete 24-attempt manifest")
    rows = []
    hashes = {}
    for spec in experiment["attempts"]:
        path = root / "attempts" / spec["attempt_id"] / "result.json"
        if not path.is_file():
            raise ValueError("Finish all scored attempts before a uniform recheck")
        row = read_json(path)
        if row["configuration_sha256"] != experiment["configuration_sha256"] or row["attempt_id"] != spec["attempt_id"]:
            raise ValueError("Attempt identity/configuration differs from the frozen manifest")
        if row.get("upload_status") != "complete" or row.get("cleanup_status") != "complete":
            raise ValueError("Complete uploads and reconcile owned resources before rechecking")
        hashes[spec["attempt_id"]] = digest(path)
        rows.append(row)
    return experiment, rows, hashes


def grade_preview(source: Path, destination: Path, image: str) -> dict:
    fingerprint = {"output_inventory": inventory(source), "checker_sha256": digest(CHECKER), "image": image}
    result_path = destination / "result.json"
    if result_path.exists():
        previous = read_json(result_path)
        if previous["fingerprint"] != fingerprint:
            raise ValueError("Recorded recheck inputs changed; preserve this recheck directory")
        return previous
    if destination.exists():
        raise ValueError(f"Incomplete recheck retained at {destination}; inspect its error and cleanup receipt")
    destination.mkdir(parents=True)
    work = destination / "work"
    copy_regular_tree(source, work / "output")
    shutil.copyfile(CHECKER, work / "preview_check.py")
    inputs = destination / "input"
    inputs.mkdir()
    box = Sandbox(work, inputs, image=image)
    result = {"fingerprint": fingerprint}
    try:
        with ExitStack() as owned:
            owned.callback(box.close)
            box.start()
            executed = box.execute("python /work/preview_check.py", timeout=45)
            result["execution"] = executed
            write_json(destination / "execution.json", executed)
            if executed["exit_code"] != 0:
                raise RuntimeError("Corrected checker did not return a result; preserve this measurement failure")
            preview = json.loads(executed["stdout"])
            if (not isinstance(preview.get("passed"), bool) or
                any(key not in preview or (preview[key] is not None and not isinstance(preview[key], bool))
                    for key in ("scrubbing", "playback", "download"))):
                raise ValueError("Corrected checker returned an invalid result contract")
            result["preview"] = preview
            try:
                result["resources"] = box.resources()
            except Exception as error:
                result["resources"] = {"container_cpu_seconds": None, "container_peak_memory_bytes": None, "limitation": str(error)}
    except BaseException:
        write_json(destination / "error.json", {**result, "error": traceback.format_exc(), "cleanup_receipt": str(box.receipt)})
        raise
    result["cleanup_receipt"] = read_json(box.receipt)
    write_json(result_path, result)
    return result


def run(root: Path, destination: Path | None = None) -> dict:
    root = root.resolve()
    destination = destination or root / "preview-recheck"
    experiment, rows, hashes = campaign(root)
    manifest = {"schema_version": 1, "experiment_id": experiment["experiment_id"],
        "configuration_sha256": experiment["configuration_sha256"],
        "original_checker_sha256": experiment["code"]["containers/preview_check.py"],
        **source_hashes(),
        "image": experiment["images"]["checker"], "original_result_sha256": hashes,
        "rule": "Recheck every visible/heldout preview whose original decoder and pixel checks passed; retain every other original criterion and every attempt"}
    path = destination / "manifest.json"
    if path.exists() and read_json(path) != manifest:
        raise ValueError("Recheck source, image or original results changed; preserve this directory")
    write_json(path, manifest)
    attempts = {}
    for row in rows:
        original = row.get("checker")
        corrected = copy.deepcopy(original)
        checks = {}
        if corrected is not None:
            for kind in ("visible", "heldout"):
                case = corrected["cases"][kind]
                if case["decoder"]["exit_code"] == 0 and case["pixels"]["passed"]:
                    checked = grade_preview(root / "attempts" / row["attempt_id"] / "checks" / kind / "verified-output",
                        destination / "attempts" / row["attempt_id"] / kind, experiment["images"]["checker"])
                    case["preview"] = checked["preview"]
                    checks[kind] = checked
            corrected["passed"] = passed_all_checks(corrected)
        attempts[row["attempt_id"]] = {"checker": corrected, "preview_rechecks": checks,
            "original_passed": original.get("passed") if original is not None else None}
    # The correction must not overwrite any original attempt or score.
    if any(digest(root / "attempts" / aid / "result.json") != sha for aid, sha in hashes.items()):
        raise ValueError("An original result changed during the recheck")
    result = {"manifest": manifest, "attempts": attempts, "complete": True}
    write_json(destination / "summary.json", result)
    return result


def publish(root: Path, destination: Path) -> dict:
    import wandb
    from forge_recovery.telemetry import credentials
    result = read_json(destination / "summary.json")
    experiment, _, hashes = campaign(root)
    if not result["complete"] or result["manifest"]["original_result_sha256"] != hashes:
        raise ValueError("Recheck is incomplete or its original records changed")
    if any(result["manifest"].get(key) != value for key, value in source_hashes().items()):
        raise ValueError("Recheck source changed after verification")
    receipt = destination / "publication.json"
    if receipt.exists():
        return read_json(receipt)
    credentials()
    with wandb.init(entity=experiment["entity"], project=experiment["project"], group=experiment["experiment_id"],
                    job_type="uniform-preview-recheck", dir=str(root),
                    settings=wandb.Settings(disable_git=True, disable_code=True, console="off")) as wandb_run:
        artifact = wandb.Artifact(experiment["experiment_id"] + "-preview-recheck", type="recovery-verification", metadata=result["manifest"])
        artifact.add_dir(str(destination), name="recheck")
        artifact.add_file(str(CHECKER), name="source/preview_check.py")
        artifact.add_file(__file__, name="source/recheck_preview.py")
        artifact.add_file(str(PACKAGE / "src/forge_recovery/judge.py"), name="source/judge.py")
        if (root / "diagnostics/clock-validation.json").exists():
            artifact.add_file(str(root / "diagnostics/clock-validation.json"), name="diagnostics/clock-validation.json")
        logged = wandb_run.log_artifact(artifact).wait()
        value = {"artifact": f"{experiment['entity']}/{experiment['project']}/{logged.name}", "digest": logged.digest, "run_url": wandb_run.url}
    write_json(receipt, value)
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    output = args.output or args.root / "preview-recheck"
    result = run(args.root, output)
    print(json.dumps({"complete": result["complete"], "attempts": len(result["attempts"])}))
    if args.publish:
        print(json.dumps(publish(args.root, output), indent=2))

from __future__ import annotations

import asyncio
from contextlib import ExitStack, contextmanager
import fcntl
import json
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

from openai import APITimeoutError
from weave.conversation import Message, start_conversation, start_turn

from .agent import REQUEST_BYTE_LIMIT, rea_session, recover, tools_for
from .benchmark import PACKAGE
from .budget import BudgetStop, Ledger, OUTPUT_LIMIT, REQUEST_RESERVATION
from .common import FAMILIES, REA_REVISION, canonical_digest, digest, inventory, read_json, verify_inventory, write_json
from .judge import copy_regular_tree, evaluate
from .sandbox import Sandbox
from .telemetry import initialize, readback, span_ids, upload_attempt, upload_prepared

MODEL = "moonshotai/Kimi-K2.7-Code"
SYSTEM = "You are an agent recovering animation behavior from shipped application artifacts. Investigate the supplied files, implement and test the requested standalone decoder, and describe your results accurately. All commands run in an isolated container. Do not claim a result you have not checked."
TASK = """Recover the animation stored at /input/animation.piskel using the minified JavaScript application in /input/bundle. Its source maps and original source are intentionally withheld.

Deliver a reusable standalone Python program /work/decode.py. It must accept:
python decode.py INPUT.piskel OUTPUT_DIRECTORY

Decode every original frame to its correctly composited RGBA PNG (including hidden frames). Write manifest.json with width, height, fps, hidden_frames (zero-based indices), playback_order (indices played, omitting hidden frames), frames (ordered PNG basenames); spritesheet.png with ALL frames in one horizontal row; and index.html.

The preview must be self-contained, initially paused, use a native-resolution canvas, a range input with accessible name Frame, a Play/Pause button, and a download link named Download sprite sheet. Scrubbing includes hidden frames; playback skips them at the recovered FPS. No network dependencies. Pillow is installed. Your decoder must write every output anew, without relying on existing output files, the supplied bundle at decoding time, or any other code file.

We will run decode.py on unseen animations from the same format family and independently compare every pixel and playback field. Malformed JSON and a missing image chunk must fail with a nonzero exit and a useful diagnostic. Artifacts are limited to 100 MiB. You have at most 40 model requests, 15 minutes and $5. Return a concise explanation when finished.
"""


def error_status(error: BaseException) -> str:
    if isinstance(error, BaseExceptionGroup):
        statuses = [error_status(e) for e in error.exceptions]
        return next((s for s in ("cancelled", "timeout", "budget_stop") if s in statuses), "infrastructure_failure")
    if isinstance(error, (asyncio.CancelledError, KeyboardInterrupt)):
        return "cancelled"
    if isinstance(error, (TimeoutError, APITimeoutError)):
        return "timeout"
    if isinstance(error, BudgetStop):
        return "budget_stop"
    return "infrastructure_failure"


def image_id(name: str) -> str:
    return subprocess.check_output(["docker", "image", "inspect", name, "--format", "{{.Id}}"], text=True, timeout=15).strip()


def code_inventory() -> dict:
    return {str(p.relative_to(PACKAGE)): digest(p) for folder in ("src", "containers", "scripts") for p in sorted((PACKAGE / folder).rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


@contextmanager
def retain_images(config: dict, root: Path):
    """Keep each frozen image in use throughout a phase, including idle arm gaps.

    An image vanished between qualification arms on the shared Docker daemon.
    Empty, network-isolated containers retain references without running agents.
    Register cleanup before startup so partial starts retain their receipts too.
    """
    with ExitStack() as resources:
        for role, image in config["images"].items():
            box = Sandbox(root / "image-retention" / role,
                          Path(config["prepared"]) / "inputs/bundle", image=image,
                          owner=config["experiment_id"] + "-retain-" + role)
            resources.callback(box.close)
            box.start()
        yield


async def freeze(root: Path, prepared: Path, entity: str) -> dict:
    if (root / "experiment.json").exists():
        value = read_json(root / "experiment.json")
        if value["entity"] != entity or value["prepared"] != str(prepared.resolve()):
            raise ValueError("Existing experiment destination/inputs differ")
        if value["code"] != code_inventory():
            raise ValueError("Code changed after freeze; preserve this experiment and use a new root")
        verify_inventory(prepared / "inputs", value["prepared_manifest"]["inputs"])
        verify_inventory(prepared / "oracle", value["prepared_manifest"]["oracle"])
        return value
    root.mkdir(parents=True, exist_ok=True)
    data = read_json(prepared / "prepared.json")
    verify_inventory(prepared / "inputs", data["inputs"])
    verify_inventory(prepared / "oracle", data["oracle"])
    if data["inputs"]["qualification/animation.piskel"] in [data["inputs"][f"{family}/animation.piskel"] for family in FAMILIES]:
        raise ValueError("Qualification must use separate artwork")
    images = {"base": image_id("rea-forge-recovery-base:v1"), "rea": image_id("rea-forge-recovery-rea:v1"), "checker": image_id("rea-forge-recovery-checker:v1")}
    with Sandbox(root / "preflight/work", prepared / "inputs/bundle", image=images["rea"]) as box:
        async with rea_session(box, True) as session:
            rea_tools = await tools_for(session)
    experiment_id = "recovery-" + uuid4().hex[:12]
    attempts = []
    for family in FAMILIES:
        for repetition in (1, 2):
            for arm in (("baseline", "rea") if repetition == 1 else ("rea", "baseline")):
                attempts.append({"fixture": family, "arm": arm, "repetition": repetition, "phase": "scored", "attempt_id": f"{experiment_id}-{family}-{arm}-{repetition}"})
    value = {"schema_version": 1, "experiment_id": experiment_id, "entity": entity, "project": "rea-showcase",
        "prepared": str(prepared.resolve()), "prepared_manifest": data, "rea_revision": REA_REVISION, "images": images,
        "model": MODEL, "base_url": "https://api.inference.wandb.ai/v1", "temperature": 0.2,
        "request_max_tokens": OUTPUT_LIMIT, "request_max_retries": 0, "request_reservation_usd": REQUEST_RESERVATION,
        "request_timeout": "remaining_agent_deadline",
        "request_serialized_byte_limit": REQUEST_BYTE_LIMIT,
        "budget": {"total_usd": 150, "attempts_usd": 130, "notebooks_usd": 20, "attempt_usd": 5, "attempt_seconds": 900, "agent_seconds": 810, "attempt_requests": 40},
        "system_prompt": SYSTEM, "task_prompt": TASK, "tools": {"baseline": await tools_for(None), "rea": rea_tools},
        "code": code_inventory(), "attempts": attempts,
        "qualification": [{"fixture": "qualification", "arm": arm, "repetition": 1, "phase": "qualification", "attempt_id": f"{experiment_id}-qualification-{arm}"} for arm in ("baseline", "rea")]}
    value["configuration_sha256"] = canonical_digest(value)
    write_json(root / "experiment.json", value)
    return value


async def export_evidence(session, box: Sandbox, root: Path, result: dict) -> None:
    if session is None:
        result["evidence_export"] = {"status": "not_applicable"}
        return
    try:
        response = await asyncio.wait_for(session.call_tool("export_evidence_bundle", {"path": "/work/complete-evidence.json"}), timeout=30)
        receipt = response.model_dump(mode="json", by_alias=True)
        if response.is_error or not (box.workspace / "complete-evidence.json").is_file():
            raise RuntimeError(json.dumps(receipt))
        (root / "evidence").mkdir()
        shutil.copyfile(box.workspace / "complete-evidence.json", root / "evidence/bundle.json")
        result["evidence_export"] = {"status": "complete", "receipt": receipt, "sha256": digest(root / "evidence/bundle.json")}
    except BaseException as error:
        result["evidence_export"] = {"status": "failed", "error": f"{type(error).__name__}: {error}"}
        if isinstance(error, asyncio.CancelledError):
            result["task_status"] = "cancelled"
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise


def finalize_agent(box: Sandbox, folder: Path, result: dict, started: float, host_cpu: float, ledger: Ledger, attempt_id: str) -> bool:
    """Finish owned resources and persist cancellation before any next stage."""
    try:
        if box.container_id:
            result["agent_resources"] = box.resources()
    except Exception as error:
        result["resource_error"] = str(error)
    try:
        box.close()
        result["cleanup_status"] = "complete" if box.container_id is None else "retry_required"
    except BaseException as error:
        result.update(cleanup_status="retry_required", cleanup_error=f"{type(error).__name__}: {error}")
        if isinstance(error, (KeyboardInterrupt, asyncio.CancelledError)):
            result["task_status"] = "cancelled"
    result.update(agent_elapsed_seconds=time.monotonic() - started,
                  controller_cpu_seconds=time.process_time() - host_cpu,
                  controller_peak_memory_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024),
                  usage=ledger.summary(attempt_id))
    result["cleanup_retry_receipts"] = [str(p) for p in folder.rglob("*.container.json") if read_json(p).get("status") != "removed"]
    if result["cleanup_retry_receipts"]:
        result["cleanup_status"] = "retry_required"
    limitation = "Controller peak memory is process-lifetime high-water, not per-attempt attribution; container memory covers the complete agent process family"
    if limitation not in result.setdefault("limitations", []):
        result["limitations"].append(limitation)
    write_json(folder / "result.json", result)
    return result["task_status"] == "cancelled"


async def attempt(config: dict, spec: dict, root: Path, ledger: Ledger) -> dict:
    folder = root / "attempts" / spec["attempt_id"]
    if folder.exists():
        if (folder / "result.json").exists():
            return read_json(folder / "result.json")
        raise RuntimeError(f"Interrupted attempt retained at {folder}; never silently replace it")
    folder.mkdir(parents=True)
    prepared = Path(config["prepared"])
    inputs = folder / "input"
    shutil.copytree(prepared / "inputs/bundle", inputs / "bundle")
    shutil.copyfile(prepared / "inputs" / spec["fixture"] / "animation.piskel", inputs / "animation.piskel")
    identity = {**spec, "experiment_id": config["experiment_id"], "configuration_sha256": config["configuration_sha256"]}
    result = {**identity, "identity": identity, "task_status": "infrastructure_failure", "upload_status": "pending",
        "conversation_id": spec["attempt_id"], "started_at_unix": time.time(), "limitations": ["Remote model CPU and memory unavailable", "Provider price estimate uses uncached rates; billing settlement is not queried"]}
    result["inputs_artifact"] = read_json(root / "inputs-publication.json")
    result["lens_url"] = f"https://forge.coreweave.com/wandb/{config['entity']}/rea-showcase/weave/agents/conversations/{spec['attempt_id']}"
    write_json(folder / "result.json", result)
    started = time.monotonic()
    host_cpu = time.process_time()
    box = Sandbox(folder / "work", inputs, image=config["images"]["rea" if spec["arm"] == "rea" else "base"], owner=spec["attempt_id"])
    result["cleanup_receipt"] = str(box.receipt)
    interrupted = False
    with start_conversation(agent_name="Piskel recovery", model=config["model"], conversation_id=spec["attempt_id"], conversation_name=f"{spec['fixture']} · {spec['arm']} · {spec['repetition']}", attributes=identity):
        with start_turn(user_message=config["task_prompt"], model=config["model"], system_instructions=[config["system_prompt"]]) as turn:
            result.update(span_ids())
            turn.set_attributes({"recovery.run_url": f"https://wandb.ai/{config['entity']}/rea-showcase/runs/{spec['attempt_id']}",
                "recovery.artifact_collection": f"{config['entity']}/rea-showcase/attempt-{spec['attempt_id']}"})
            try:
                box.start()
                async with rea_session(box, spec["arm"] == "rea") as session:
                    try:
                        recovered = await recover(box, session, config, spec["attempt_id"], ledger, folder, started + 810)
                        result["completion"] = recovered["completion"]
                        turn.output_messages = [Message(role="assistant", content=recovered["completion"])]
                        result["task_status"] = "submitted"
                    finally:
                        await export_evidence(session, box, folder, result)
            except BaseException as error:
                result.update(task_status=error_status(error), error=f"{type(error).__name__}: {error}")
                turn.record_error(error)
                interrupted = result["task_status"] == "cancelled"
            finally:
                interrupted = finalize_agent(box, folder, result, started, host_cpu, ledger, spec["attempt_id"]) or interrupted
    interrupted = interrupted or result["task_status"] == "cancelled"
    if result["cleanup_status"] == "complete" and (folder / "work").exists():
        try:
            copy_regular_tree(folder / "work", folder / "submission")
            if not interrupted:
                result["checker"] = await asyncio.to_thread(evaluate, folder / "submission", prepared / "oracle" / spec["fixture"], folder / "checks", config["images"], started + 900)
                if result["task_status"] == "submitted":
                    result["task_status"] = "success" if result["checker"]["passed"] else "task_failure"
        except Exception as error:
            result["checker_error"] = f"{type(error).__name__}: {error}"
            if result["task_status"] == "submitted":
                result["task_status"] = "timeout" if isinstance(error, TimeoutError) else "infrastructure_failure"
    result["total_elapsed_seconds"] = time.monotonic() - started
    result["cleanup_retry_receipts"] = [str(p) for p in folder.rglob("*.container.json") if read_json(p).get("status") != "removed"]
    if result["cleanup_retry_receipts"]:
        result["cleanup_status"] = "retry_required"
    write_json(folder / "result.json", result)
    if not interrupted:
        try:
            result["lens_readback"] = await asyncio.to_thread(readback, config["entity"], spec["attempt_id"], folder / "lens-readback.json")
            result["lens_status"] = "verified"
        except Exception as error:
            result.update(lens_status="failed", lens_error=str(error))
        write_json(folder / "result.json", result)
        try:
            result["publication"] = await asyncio.to_thread(upload_attempt, config["entity"], folder, result)
            result["upload_status"] = "complete"
        except Exception as error:
            result.update(upload_status="failed", upload_error=str(error))
        write_json(folder / "result.json", result)
    print(json.dumps({k: result.get(k) for k in ("attempt_id", "task_status", "upload_status", "usage")}), flush=True)
    if interrupted:
        raise asyncio.CancelledError("Attempt cancelled; local results and cleanup receipt retained")
    return result


async def execute(root: Path, prepared: Path, entity: str, phase: str, ledger_path: Path) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    with (root / "controller.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        config = await freeze(root, prepared, entity)
        initialize(entity)
        if not (root / "inputs-publication.json").exists():
            write_json(root / "inputs-publication.json", await asyncio.to_thread(upload_prepared, entity, root, prepared, config))
        if phase == "scored":
            qualification = read_json(root / "qualification.json")
            if not qualification["qualified"]:
                raise RuntimeError("Qualification failed; do not launch scored attempts")
        with retain_images(config, root):
            for current in (("qualification", "scored") if phase == "all" else (phase,)):
                rows = []
                for spec in config["qualification" if current == "qualification" else "attempts"]:
                    rows.append(await attempt(config, spec, root, Ledger(ledger_path)))
                    if rows[-1].get("cleanup_status") != "complete":
                        raise RuntimeError("Cleanup requires retry before further execution")
                if current == "qualification":
                    qualified = all(r.get("task_status") in ("success", "task_failure", "budget_stop", "timeout") and r.get("lens_status") == "verified" and r.get("upload_status") == "complete" and r.get("evidence_export", {}).get("status") in ("complete", "not_applicable") and any(e["kind"] == "tool" for e in read_json(root / "attempts" / r["attempt_id"] / "events.json")) for r in rows)
                    write_json(root / "qualification.json", {"qualified": qualified, "attempts": [r["attempt_id"] for r in rows]})
                    if phase == "all" and not qualified:
                        raise RuntimeError("Qualification failed; no scored attempts launched")
        return summarize(root)


def summarize(root: Path) -> dict:
    manifest = read_json(root / "experiment.json")
    rows = [read_json(root / "attempts" / s["attempt_id"] / "result.json") for s in manifest["attempts"] if (root / "attempts" / s["attempt_id"] / "result.json").exists()]
    value = {"experiment_id": manifest["experiment_id"], "configuration_sha256": manifest["configuration_sha256"], "planned_scored": 24, "recorded_scored": len(rows), "attempts": rows, "arms": {}}
    for arm in ("baseline", "rea"):
        selected = [r for r in rows if r["arm"] == arm]
        value["arms"][arm] = {"recorded": len(selected), "passed": sum(bool(r.get("checker", {}).get("passed")) for r in selected), "statuses": {status: sum(r["task_status"] == status for r in selected) for status in sorted({r["task_status"] for r in selected})}}
    write_json(root / "summary.json", value)
    return value

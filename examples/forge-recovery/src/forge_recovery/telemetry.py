from __future__ import annotations

import netrc
import os
from pathlib import Path

import httpx
import wandb
import weave
from opentelemetry import trace
from weave.conversation import Message, TextPart, ToolCallPart, ToolCallResponsePart

from .common import write_json


def credentials() -> str:
    key = os.environ.get("WANDB_API_KEY")
    if not key:
        auth = netrc.netrc().authenticators("api.wandb.ai")
        if not auth:
            raise RuntimeError("Authenticate Forge before running the controller")
        key = auth[2]
        os.environ["WANDB_API_KEY"] = key
    return key


def ensure_private_project(entity: str) -> dict:
    credentials()
    api = wandb.Api()
    query = "query($e:String!){project(name:\"rea-showcase\",entityName:$e){name access}}"
    project = api._service_api.execute_graphql(query, {"e": entity})["project"]
    if project is None:
        query = 'mutation($e:String!){upsertModel(input:{name:"rea-showcase",entityName:$e,access:"PRIVATE"}){project{name access}}}'
        project = api._service_api.execute_graphql(query, {"e": entity})["upsertModel"]["project"]
    if project["access"].upper() != "PRIVATE":
        raise ValueError("The destination project is not private")
    return project


def initialize(entity: str):
    ensure_private_project(entity)
    # This pinned SDK uses explicit opt-in patching. Spans below are manual.
    return weave.init(f"{entity}/rea-showcase")


def message(value: dict) -> Message:
    parts = []
    if value.get("content"):
        parts.append(TextPart(content=value["content"]))
    for call in value.get("tool_calls") or []:
        parts.append(ToolCallPart(id=call["id"], name=call["function"]["name"], arguments=call["function"]["arguments"]))
    if value["role"] == "tool":
        parts = [ToolCallResponsePart(id=value["tool_call_id"], response=value["content"])]
    return Message(role=value["role"], parts=parts, tool_call_id=value.get("tool_call_id", ""))


def span_ids() -> dict:
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        raise RuntimeError("Conversation SDK did not initialize a real trace provider")
    return {"trace_id": format(context.trace_id, "032x"), "span_id": format(context.span_id, "016x")}


def readback(entity: str, conversation_id: str, destination: Path) -> dict:
    provider = trace.get_tracer_provider()
    if not provider.force_flush(timeout_millis=15000):
        raise RuntimeError("Conversation export flush timed out")
    with httpx.Client(auth=("api", credentials()), timeout=30) as client:
        response = client.post("https://trace.wandb.ai/agents/conversations/chat", json={
            "project_id": f"{entity}/rea-showcase", "conversation_id": conversation_id,
            "limit": 50, "offset": 0,
        })
        response.raise_for_status()
        value = response.json()
        if not value.get("turns"):
            raise RuntimeError("Exported conversation is not yet visible in Agent Lens readback")
        spans = []
        for turn in value["turns"]:
            offset = 0
            while True:
                response = client.post("https://trace.wandb.ai/agents/spans/query", json={
                    "project_id": f"{entity}/rea-showcase", "include_details": True,
                    "query": {"$expr": {"$eq": [{"$getField": "trace_id"}, {"$literal": turn["trace_id"]}]}},
                    "limit": 50, "offset": offset,
                })
                response.raise_for_status()
                page = response.json()
                current = page.get("spans", [])
                spans.extend(current)
                offset += len(current)
                if offset >= page.get("total_count", 0) or not current:
                    break
        value["spans"] = spans
        write_json(destination, value)
        roots = {s["span_id"] for s in spans if s["operation_name"] == "invoke_agent"}
        children = [s for s in spans if s["operation_name"] in ("chat", "execute_tool")]
        if not roots or any(s["parent_span_id"] not in roots for s in children):
            raise RuntimeError("Agent Lens span nesting does not match the root agent turn")
        return {"turns": len(value["turns"]), "spans": len(spans), "total_turns": value.get("total_turns"), "has_more": value.get("has_more")}


def upload_attempt(entity: str, root: Path, result: dict) -> dict:
    with wandb.init(entity=entity, project="rea-showcase", id=result["attempt_id"],
                    group=result["experiment_id"], job_type=result["phase"],
                    config=result["identity"], dir=str(root),
                    settings=wandb.Settings(disable_git=True, disable_code=True, console="off")) as run:
        run.summary.update({"task_status": result["task_status"], "passed": result.get("checker", {}).get("passed", False), **result["usage"]})
        artifact = wandb.Artifact("attempt-" + result["attempt_id"], type="recovery-attempt", metadata=result["identity"])
        for name in ("result.json", "messages.json", "events.json", "lens-readback.json"):
            if (root / name).exists():
                artifact.add_file(str(root / name), name=name)
        for name in ("submission", "evidence", "checks"):
            if (root / name).exists():
                artifact.add_dir(str(root / name), name=name)
        logged = run.log_artifact(artifact).wait()
        return {"run_id": run.id, "run_url": run.url, "artifact": f"{entity}/rea-showcase/{logged.name}", "artifact_digest": logged.digest}


def upload_prepared(entity: str, root: Path, prepared: Path, experiment: dict) -> dict:
    with wandb.init(entity=entity, project="rea-showcase", id=experiment["experiment_id"],
                    job_type="frozen-inputs", dir=str(root),
                    settings=wandb.Settings(disable_git=True, disable_code=True, console="off")) as run:
        artifact = wandb.Artifact(experiment["experiment_id"] + "-inputs", type="recovery-inputs",
                                  metadata={"configuration_sha256": experiment["configuration_sha256"]})
        artifact.add_file(str(root / "experiment.json"), name="experiment.json")
        artifact.add_file(str(prepared / "prepared.json"), name="prepared.json")
        artifact.add_dir(str(prepared / "inputs"), name="inputs")
        artifact.add_dir(str(prepared / "oracle"), name="oracle")
        logged = run.log_artifact(artifact).wait()
        return {"artifact": f"{entity}/rea-showcase/{logged.name}", "artifact_digest": logged.digest, "run_url": run.url}

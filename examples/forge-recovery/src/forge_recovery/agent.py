from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI
from weave.conversation import Usage, start_llm, start_tool

from .budget import BudgetStop, Ledger, OUTPUT_LIMIT
from .common import write_json
from .sandbox import Sandbox
from .telemetry import credentials, message, span_ids

REA_TOOLS = ("analyze_javascript_application", "trace_application_feature", "trace_javascript_semantics", "inspect_analysis_view", "get_evidence_bundle")
EXECUTE = {"type": "function", "function": {"name": "execute", "description": "Run shell commands in the isolated workspace /work. Python with Pillow, Node, and ripgrep are installed. /input is read-only; no network. Read files, search code, write and test your decoder. Output is bounded to 64 KiB per stream.", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"], "additionalProperties": False}}}


@asynccontextmanager
async def rea_session(box: Sandbox, enabled: bool):
    if not enabled:
        yield None
        return
    parameters = StdioServerParameters(command="docker", args=["exec", "-i", "-w", "/work", box.container_id, "node", "/opt/rea/scripts/rea.mjs", "mcp"])
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=180) as session:
            await session.initialize()
            yield session


async def tools_for(session) -> list[dict]:
    result = [EXECUTE]
    if session is not None:
        catalog = {t.name: t for t in (await session.list_tools()).tools}
        for name in REA_TOOLS:
            tool = catalog[name]
            result.append({"type": "function", "function": {"name": name, "description": tool.description, "parameters": tool.input_schema}})
    return result


def delivered_result(value: dict, location: str) -> str:
    """Canonical result remains unmodified on disk; only oversize delivery is bounded."""
    serialized = json.dumps(value, ensure_ascii=False)
    if len(serialized.encode()) <= 32768:
        return serialized
    structured = value.get("structured_content") or value.get("structuredContent") or {}
    return json.dumps({"delivery": "oversize result retained", "complete_result_path": location,
                       "evidence_id": structured.get("evidence_id"),
                       "parent_evidence_id": structured.get("normalized_result", {}).get("parent_evidence_id"),
                       "instruction": "Read selected fields from the complete JSON file with execute, or request a smaller inspect_analysis_view page. This receipt does not replace canonical Evidence."})


async def recover(box: Sandbox, session, config: dict, attempt_id: str, ledger: Ledger, root: Path, deadline: float) -> dict:
    messages = [{"role": "system", "content": config["system_prompt"]}, {"role": "user", "content": config["task_prompt"]}]
    toolset = await tools_for(session)
    if toolset != config["tools"]["rea" if session else "baseline"]:
        raise RuntimeError("Live tool schemas differ from the frozen manifest")
    events = []
    client = AsyncOpenAI(api_key=credentials(), base_url=config["base_url"], max_retries=0, timeout=180)
    try:
        for index in range(40):
            if time.monotonic() >= deadline:
                raise TimeoutError("Attempt exceeded 15 minutes")
            # A conservative bound on content before the server's context admission.
            if len(json.dumps({"messages": messages, "tools": toolset}).encode()) > 220000:
                raise BudgetStop("Context bound reached; no silent truncation")
            reservation = ledger.reserve(attempt_id)
            with start_llm(model=config["model"], provider_name="forge") as span:
                ids = span_ids()
                span.input_messages = [message(m) for m in messages]
                span.request_max_tokens = OUTPUT_LIMIT
                span.request_temperature = config["temperature"]
                span.set_attributes({"recovery.tool_definitions": json.dumps(toolset)})
                try:
                    response = await client.chat.completions.create(model=config["model"], messages=messages, tools=toolset,
                        temperature=config["temperature"], max_tokens=OUTPUT_LIMIT,
                        timeout=min(180, max(1, deadline - time.monotonic())))
                    usage = response.usage.model_dump() if response.usage else None
                    ledger.settle(reservation, usage)
                    if usage:
                        span.usage = Usage(input_tokens=usage["prompt_tokens"], output_tokens=usage["completion_tokens"], total_tokens=usage["total_tokens"])
                    span.response_id = response.id
                    span.response_model = response.model
                    reply = response.choices[0].message.model_dump(exclude_none=True)
                    span.output_messages = [message(reply)]
                    span.finish_reasons = [response.choices[0].finish_reason]
                except BaseException as error:
                    # Never retry an uncertain paid request. Its reservation stays charged.
                    span.record_error(error)
                    events.append({"kind": "model_error", "request": index, **ids, "error": str(error)})
                    raise
            events.append({"kind": "model", "request": index, **ids, "usage": usage})
            messages.append(reply)
            write_json(root / "messages.json", messages)
            if not reply.get("tool_calls"):
                return {"completion": reply.get("content", ""), "events": events}
            for call in reply["tool_calls"]:
                function = call["function"]
                name = function["name"]
                with start_tool(name=name, arguments=function["arguments"], tool_call_id=call["id"]) as span:
                    ids = span_ids()
                    try:
                        arguments = json.loads(function["arguments"])
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError("Attempt exceeded 15 minutes")
                        if name == "execute":
                            value = await asyncio.to_thread(box.execute, arguments["command"], timeout=min(60, remaining))
                            delivered = json.dumps(value)
                            if value["exit_code"] != 0:
                                span.record_error(RuntimeError(f"Command exited {value['exit_code']}"))
                        elif session is not None and name in REA_TOOLS:
                            response = await asyncio.wait_for(session.call_tool(name, arguments), timeout=min(180, remaining))
                            value = response.model_dump(mode="json", by_alias=True)
                            path = box.workspace / "tool-results" / f"{len(events):04}.json"
                            write_json(path, value)
                            delivered = delivered_result(value, "/work/" + str(path.relative_to(box.workspace)))
                            if response.is_error:
                                span.record_error(RuntimeError("REA returned a tool error"))
                        else:
                            raise ValueError("Tool is not exposed in this arm")
                    except (TimeoutError, asyncio.CancelledError):
                        raise
                    except Exception as error:
                        span.record_error(error)
                        delivered = json.dumps({"error": f"{type(error).__name__}: {error}"})
                    span.result = delivered
                events.append({"kind": "tool", "tool": name, "tool_call_id": call["id"], **ids})
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": delivered})
                write_json(root / "messages.json", messages)
                write_json(root / "events.json", events)
        raise BudgetStop("40 model requests exhausted")
    finally:
        write_json(root / "messages.json", messages)
        write_json(root / "events.json", events)
        await client.close()

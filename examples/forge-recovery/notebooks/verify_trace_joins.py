"""Reconcile recorded messages and tool events with the stored Agent Lens readback."""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
import hashlib
import json
from pathlib import Path


def recorded_value(value):
    """Compare JSON payloads across the SDK's string serialization boundary."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            pass
    return value


def verify_attempt(folder: Path) -> dict:
    names = ("result.json", "messages.json", "events.json", "lens-readback.json")
    records = {name: json.loads((folder / name).read_text()) for name in names}
    result = records["result.json"]
    if "total_elapsed_seconds" not in result or result.get("lens_status") != "verified":
        raise ValueError(f"Attempt is not finalized with an Agent Lens readback: {folder.name}")
    spans = records["lens-readback.json"]["spans"]
    by_identity = {(s["trace_id"], s["span_id"]): s for s in spans}
    assert len(by_identity) == len(spans), "Duplicate span identity"
    roots = {(s["trace_id"], s["span_id"]) for s in spans if s["operation_name"] == "invoke_agent"}
    assert len(roots) == 1
    children = [s for s in spans if s["operation_name"] in ("chat", "execute_tool")]
    assert all((s["trace_id"], s["parent_span_id"]) in roots and s["conversation_id"] == result["attempt_id"] for s in children)
    tool_events = [e for e in records["events.json"] if e["kind"] == "tool"]
    joined = []
    for event in tool_events:
        span = by_identity[event["trace_id"], event["span_id"]]
        assert span["operation_name"] == "execute_tool"
        assert span["tool_call_id"] == event["tool_call_id"]
        assert span["tool_name"] == event["tool"]
        joined.append({"trace_id": event["trace_id"], "span_id": event["span_id"],
                       "tool_call_id": event["tool_call_id"], "tool": event["tool"],
                       "status_code": span["status_code"]})
    # Match response occurrences in order. A provider may reuse an ID on a later
    # request; do not collapse those occurrences into a single message or span.
    pending = defaultdict(deque)
    content_matches = 0
    for message in records["messages.json"]:
        if message["role"] == "assistant":
            for call in message.get("tool_calls") or []:
                pending[call["id"]].append(call)
        elif message["role"] == "tool":
            call_id = message["tool_call_id"]
            assert pending[call_id], "Tool response has no preceding matching request"
            request = pending[call_id].popleft()
            event = tool_events[content_matches]
            assert event["tool_call_id"] == call_id
            span = by_identity[event["trace_id"], event["span_id"]]
            assert recorded_value(request["function"]["arguments"]) == recorded_value(span["tool_call_arguments"])
            assert recorded_value(message["content"]) == recorded_value(span["tool_call_result"])
            content_matches += 1
    assert content_matches == len(tool_events)
    model_spans = [s for s in spans if s["operation_name"] == "chat"]
    assert len(model_spans) == result["usage"]["requests"]
    joined_ids = {(e["trace_id"], e["span_id"]) for e in tool_events}
    return {"attempt_id": result["attempt_id"], "model_spans": len(model_spans),
            "returned_tool_events": len(joined), "joins": joined,
            "argument_and_response_pairs_matched": content_matches,
            "unanswered_declared_tool_calls": {key: len(calls) for key, calls in pending.items() if calls},
            "tool_spans_without_returned_event": [
                {key: span[key] for key in ("trace_id", "span_id", "tool_call_id", "status_code")}
                for span in spans if span["operation_name"] == "execute_tool"
                and (span["trace_id"], span["span_id"]) not in joined_ids],
            "source_sha256": {name: hashlib.sha256((folder / name).read_bytes()).hexdigest() for name in names}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    experiment = json.loads((root / "experiment.json").read_text())
    assert len(experiment["attempts"]) == 24
    records = [verify_attempt(root / "attempts" / spec["attempt_id"]) for spec in experiment["attempts"]]
    receipt = {"attempts": records, "verified_attempts": len(records),
               "returned_tool_events": sum(r["returned_tool_events"] for r in records),
               "argument_and_response_pairs_matched": sum(r["argument_and_response_pairs_matched"] for r in records),
               "model_spans": sum(r["model_spans"] for r in records),
               "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "scope": "Identity, parentage, tool arguments and delivered response reconciliation against stored real server readbacks. JSON payloads are compared after parsing. Unanswered calls and spans without returned events remain explicit; agreement does not validate the tool's substantive answer."}
    (root / "lens-integrity-final.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({key: receipt[key] for key in ("verified_attempts", "returned_tool_events", "model_spans")}))


if __name__ == "__main__":
    main()

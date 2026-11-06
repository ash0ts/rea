import asyncio
import json
from pathlib import Path

import pytest

from forge_recovery.budget import BudgetStop, Ledger, REQUEST_RESERVATION
from forge_recovery.common import read_json
from forge_recovery.experiment import error_status, export_evidence
from forge_recovery.judge import copy_regular_tree, stage_decoder
from forge_recovery.telemetry import message


def test_unknown_requests_survive_controller_restart_and_stop_budget(tmp_path):
    ledger = Ledger(tmp_path / "ledger.json")
    admitted = int(5 / REQUEST_RESERVATION)
    for _ in range(admitted):
        ledger.reserve("interrupted")
    resumed = Ledger(tmp_path / "ledger.json")
    with pytest.raises(BudgetStop):
        resumed.reserve("interrupted")
    assert resumed.summary("interrupted")["unknown_usage_requests"] == admitted
    assert resumed.summary()["reserved_or_estimated_usd"] == pytest.approx(admitted * REQUEST_RESERVATION)


def test_global_budget_reserves_notebook_allowance(tmp_path):
    ledger = Ledger(tmp_path / "ledger.json")
    with pytest.raises(BudgetStop, match="Campaign"):
        for i in range(1000):
            ledger.reserve(str(i))
    assert ledger.summary()["reserved_or_estimated_usd"] <= 130


def test_usage_reconciles_and_never_exempts_request_limit(tmp_path):
    ledger = Ledger(tmp_path / "ledger.json")
    for _ in range(40):
        key = ledger.reserve("a")
        ledger.settle(key, {"prompt_tokens": 100, "completion_tokens": 10})
    with pytest.raises(BudgetStop):
        ledger.reserve("a")
    assert ledger.summary()["input_tokens"] == 4000
    assert ledger.summary()["unknown_usage_requests"] == 0


def test_submission_outputs_are_not_reused_by_judge(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "decode.py").write_text("raise RuntimeError('not implemented')")
    (candidate / "manifest.json").write_text('{}')
    stage_decoder(candidate, tmp_path / "check")
    assert sorted(p.name for p in (tmp_path / "check").iterdir()) == ["decode.py"]


def test_upload_boundary_rejects_symlinks(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "escape").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="nonregular"):
        copy_regular_tree(candidate, tmp_path / "copy")


@pytest.mark.parametrize("failure", [RuntimeError("export failed"), asyncio.CancelledError()])
def test_export_failure_or_cancellation_during_finalization_is_retained(tmp_path, failure):
    class Session:
        async def call_tool(self, *_):
            raise failure
    class Box:
        workspace = tmp_path
    result = {}
    asyncio.run(export_evidence(Session(), Box(), tmp_path, result))
    assert result["evidence_export"]["status"] == "failed"
    assert not (tmp_path / "evidence").exists()


def test_nested_mcp_failures_preserve_timeout_and_budget_categories():
    assert error_status(ExceptionGroup("mcp", [ExceptionGroup("inner", [TimeoutError()])])) == "timeout"
    assert error_status(ExceptionGroup("mcp", [BudgetStop()])) == "budget_stop"


def test_conversation_tool_ids_survive_message_conversion():
    call = message({"role": "assistant", "tool_calls": [{"id": "call_1", "function": {"name": "execute", "arguments": '{"command":"pwd"}'}}]})
    reply = message({"role": "tool", "tool_call_id": "call_1", "content": '{"stdout":"/work"}'})
    assert call.parts[0].id == reply.parts[0].id == "call_1"


def test_real_sdk_accepts_frozen_agent_turn_configuration():
    from weave.conversation import Turn
    from forge_recovery.experiment import SYSTEM, TASK, MODEL
    turn = Turn(model=MODEL, system_instructions=[SYSTEM], messages=[message({"role": "user", "content": TASK})])
    assert turn.system_instructions == [SYSTEM]


@pytest.mark.parametrize("with_tool", [True, False])
def test_truncated_model_output_stops_before_execution_or_replay(tmp_path, monkeypatch, with_tool):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock
    from openai.types.chat import ChatCompletion
    from forge_recovery import agent
    reply = {"role": "assistant", "content": "partial"}
    if with_tool:
        reply["tool_calls"] = [{"id": "call_partial", "type": "function", "function": {"name": "execute", "arguments": '{"command":"unfinished'}}]
    response = ChatCompletion.model_validate({"id": "response", "object": "chat.completion", "created": 1, "model": "test", "choices": [{"index": 0, "finish_reason": "length", "message": reply}], "usage": {"prompt_tokens": 100, "completion_tokens": 8192, "total_tokens": 8292}})
    create = AsyncMock(return_value=response)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)), close=AsyncMock())
    class Span:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def set_attributes(self, *_): pass
    monkeypatch.setattr(agent, "credentials", lambda: "test-key")
    monkeypatch.setattr(agent, "AsyncOpenAI", lambda **_: client)
    monkeypatch.setattr(agent, "start_llm", lambda **_: Span())
    monkeypatch.setattr(agent, "span_ids", lambda: {"span_id": "span", "trace_id": "trace"})
    box = SimpleNamespace(execute=Mock(side_effect=AssertionError("partial tool call must not execute")))
    config = {"system_prompt": "system", "task_prompt": "task", "model": "test", "temperature": 0.2, "base_url": "https://example.invalid", "tools": {"baseline": [agent.EXECUTE]}}
    ledger = Ledger(tmp_path / "ledger.json")
    with pytest.raises(BudgetStop, match="output token limit"):
        asyncio.run(agent.recover(box, None, config, "attempt", ledger, tmp_path, float("inf")))
    assert create.await_count == 1
    box.execute.assert_not_called()
    assert read_json(tmp_path / "messages.json")[-1] == response.choices[0].message.model_dump(exclude_none=True)
    assert read_json(tmp_path / "events.json")[-1]["finish_reason"] == "length"
    assert ledger.summary("attempt")["output_tokens"] == 8192
    client.close.assert_awaited_once()


@pytest.mark.parametrize("valid_exit, expected", [(2, False), (1, False), (0, True)])
def test_invalid_input_checks_require_working_valid_input_control(tmp_path, monkeypatch, valid_exit, expected):
    from forge_recovery import judge
    from forge_recovery.common import write_json
    oracle = tmp_path / "oracle"
    for kind in ("visible", "heldout"):
        write_json(oracle / kind / "animation.piskel", {"piskel": {"layers": [json.dumps({"chunks": []})]}})
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    class Box:
        def __init__(self, work, inputs, **_): self.inputs = inputs
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def resources(self): return {}
        def execute(self, command, **_):
            return {"exit_code": 1 if self.inputs.name == "invalid-input" else valid_exit, "stdout": "", "stderr": "input rejected or decoder unavailable"}
    monkeypatch.setattr(judge, "Sandbox", Box)
    monkeypatch.setattr(judge, "grade", lambda *_: {"passed": False})
    result = judge.evaluate(candidate, oracle, tmp_path / "check", {"base": "test", "checker": "test"})
    assert all(r["passed"] is expected for r in result["regressions"].values())
    assert all(r["valid_input_control_passed"] is expected for r in result["regressions"].values())

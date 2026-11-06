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
    for _ in range(23):
        ledger.reserve("interrupted")
    resumed = Ledger(tmp_path / "ledger.json")
    with pytest.raises(BudgetStop):
        resumed.reserve("interrupted")
    assert resumed.summary("interrupted")["unknown_usage_requests"] == 23
    assert resumed.summary()["reserved_or_estimated_usd"] == pytest.approx(23 * REQUEST_RESERVATION)


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

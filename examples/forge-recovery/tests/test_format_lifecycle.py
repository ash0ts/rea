"""Failure injection at the format-study controller, without paid calls."""
import asyncio
import importlib.util
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from forge_recovery.budget import BudgetStop
from forge_recovery.common import read_json, write_json


@pytest.fixture
def harness(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "format_recovery"
    monkeypatch.syspath_prepend(str(source))
    spec = importlib.util.spec_from_file_location("format_study_run", source / "run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    inputs = tmp_path / "prepared/inputs/chunks"
    inputs.mkdir(parents=True)
    (inputs / "sample-0.bin").write_bytes(b"fixture")
    root = tmp_path / "experiment"
    root.mkdir()
    conf = {"prepared": str(tmp_path / "prepared"), "experiment_id": "test", "configuration_sha256": "hash",
            "images": {"base": "test", "rea": "test", "checker": "test"}, "model": "test"}
    attempt_spec = {"attempt_id": "a", "fixture": "chunks", "arm": "baseline", "repetition": 1, "phase": "scored"}

    class Context:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def record_error(self, *_): pass

    class Box:
        cancel_close = False
        instances = []
        def __init__(self, workspace, inputs, **kwargs):
            self.workspace = workspace
            self.receipt = workspace.parent / "work.container.json"
            self.owner = kwargs["owner"]
            self.container_id = None
            self.instances.append(self)
        def start(self):
            self.workspace.mkdir()
            (self.workspace / "decode.py").write_text("print('saved candidate')\n")
            self.container_id = "owned"
            write_json(self.receipt, {"status": "running", "id": self.container_id, "owner": self.owner})
        def resources(self): return {"container_cpu_seconds": 1}
        def close(self):
            if self.cancel_close: raise asyncio.CancelledError()
            write_json(self.receipt, {"status": "removed", "id": self.container_id, "owner": self.owner})
            self.container_id = None

    @asynccontextmanager
    async def session(*_): yield None
    async def recover(*_): return {"completion": "submitted"}
    async def export(_session, _box, _folder, result): result["evidence_export"] = {"status": "not_applicable"}
    monkeypatch.setattr(module, "Sandbox", Box)
    monkeypatch.setattr(module, "start_conversation", lambda **_: Context())
    monkeypatch.setattr(module, "start_turn", lambda **_: Context())
    monkeypatch.setattr(module, "span_ids", lambda: {"trace_id": "trace", "span_id": "span"})
    monkeypatch.setattr(module, "rea_session", session)
    monkeypatch.setattr(module, "recover", recover)
    monkeypatch.setattr(module, "export_evidence", export)
    monkeypatch.setattr(module, "evaluate", lambda *_: {"passed": True, "behavior_pass": True})
    monkeypatch.setattr(module, "readback", lambda *_: {"verified": True})
    monkeypatch.setattr(module, "upload_attempt", lambda *_: {"artifact": "test/evidence:v0"})
    return module, conf, attempt_spec, root, Box


def test_budget_stop_retains_and_checks_the_saved_program(harness, monkeypatch):
    module, conf, spec, root, box = harness
    async def stop(*_): raise BudgetStop("request allowance exhausted")
    monkeypatch.setattr(module, "recover", stop)
    result = asyncio.run(module.attempt(conf, spec, root))
    assert result["task_status"] == "budget_stop"
    assert result["checker"]["passed"]
    assert (root / "attempts/a/submission/decode.py").is_file()
    assert result["cleanup_status"] == "complete" and box.instances[0].container_id is None


def test_request_cap_refuses_the_twenty_fifth_reservation(harness):
    module, _, _, root, _ = harness
    ledger = module.AttemptLedger(root / "budget.json")
    for _ in range(24):
        reservation = ledger.reserve("a")
        ledger.settle(reservation, {"prompt_tokens": 1, "completion_tokens": 1})
    with pytest.raises(BudgetStop, match="24 model requests"):
        ledger.reserve("a")
    assert ledger.summary("a")["requests"] == 24
    assert len(read_json(root / "budget.json")["requests"]) == 24


def test_export_and_upload_failures_do_not_erase_checked_result(harness, monkeypatch):
    module, conf, spec, root, _ = harness
    async def export(_session, _box, _folder, result):
        result["evidence_export"] = {"status": "failed", "error": "export unavailable"}
    def fail(*_): raise OSError("upload unavailable")
    monkeypatch.setattr(module, "export_evidence", export)
    monkeypatch.setattr(module, "upload_attempt", fail)
    result = asyncio.run(module.attempt(conf, spec, root))
    assert result["task_status"] == "success" and result["checker"]["passed"]
    assert result["upload_status"] == "failed"
    assert result["evidence_export"]["status"] == "failed"
    assert read_json(root / "attempts/a/result.json") == result


def test_cancellation_during_final_cleanup_keeps_identity_and_stop_reason(harness):
    module, conf, spec, root, box = harness
    box.cancel_close = True
    with pytest.raises(asyncio.CancelledError): asyncio.run(module.attempt(conf, spec, root))
    result = read_json(root / "attempts/a/result.json")
    assert result["task_status"] == "cancelled"
    assert result["cleanup_status"] == "retry_required"
    assert result["cleanup_retry_receipts"] == [str(root / "attempts/a/work.container.json")]
    receipt = read_json(Path(result["cleanup_retry_receipts"][0]))
    assert receipt["owner"] == "a" and receipt["id"] == "owned"
    assert box.instances[0].container_id == "owned"
    assert (root / "attempts/a/work/decode.py").is_file()


def test_cancellation_recorded_during_evidence_export_stops_before_checking(harness, monkeypatch):
    module, conf, spec, root, box = harness
    async def cancel(_session, _box, _folder, result):
        result["evidence_export"] = {"status": "failed", "error": "CancelledError"}
        result["task_status"] = "cancelled"
    def forbidden(*_): pytest.fail("Cancellation must stop before checker or upload")
    monkeypatch.setattr(module, "export_evidence", cancel)
    monkeypatch.setattr(module, "evaluate", forbidden)
    monkeypatch.setattr(module, "upload_attempt", forbidden)
    with pytest.raises(asyncio.CancelledError): asyncio.run(module.attempt(conf, spec, root))
    result = read_json(root / "attempts/a/result.json")
    assert result["task_status"] == "cancelled" and result["cleanup_status"] == "complete"
    assert box.instances[0].container_id is None
    assert (root / "attempts/a/work/decode.py").is_file()


@pytest.mark.parametrize("stage", ["cleanup", "export"])
def test_dependency_controller_uses_the_same_finalization_policy(harness, monkeypatch, stage):
    import shutil
    from forge_recovery.budget import Ledger
    format_module, conf, spec, root, box = harness
    source = Path(__file__).resolve().parents[1] / "dependency_review/run.py"
    # Each executable companion owns modules with the same script-local names.
    # Load the dependency companion's real modules without leaking them to other tests.
    import sys
    for name in ("fixtures", "checker"):
        local_spec = importlib.util.spec_from_file_location(name, source.parent / (name + ".py"))
        local_module = importlib.util.module_from_spec(local_spec)
        monkeypatch.setitem(sys.modules, name, local_module)
        local_spec.loader.exec_module(local_module)
    import_spec = importlib.util.spec_from_file_location("dependency_study_run", source)
    module = importlib.util.module_from_spec(import_spec)
    import_spec.loader.exec_module(module)
    shutil.copytree(Path(conf["prepared"]) / "inputs", root / "prepared/inputs")
    for name in ("Sandbox", "start_conversation", "start_turn", "span_ids", "rea_session", "export_evidence"):
        monkeypatch.setattr(module, name, getattr(format_module, name))
    async def review(*_): return "{}"
    monkeypatch.setattr(module, "review_agent", review)
    monkeypatch.setattr(module, "parse_submission", lambda _: {})
    monkeypatch.setattr(module, "evaluate", lambda *_: {"passed": True})
    def forbidden(*_): pytest.fail("Cancelled attempt must not export telemetry or upload")
    monkeypatch.setattr(module, "readback", forbidden)
    monkeypatch.setattr(module, "publish", forbidden)
    if stage == "cleanup":
        box.cancel_close = True
    else:
        async def cancel(_session, _box, _folder, result):
            result["evidence_export"] = {"status": "failed", "error": "CancelledError"}
            result["task_status"] = "cancelled"
        monkeypatch.setattr(module, "export_evidence", cancel)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(module.attempt(conf, spec, root, Ledger(root / "budget.json"), {"chunks": {}}))
    result = read_json(root / "attempts/a/result.json")
    assert result["task_status"] == "cancelled"
    assert result["cleanup_status"] == ("retry_required" if stage == "cleanup" else "complete")
    assert bool(result["cleanup_retry_receipts"]) == (stage == "cleanup")
    assert result["checker"]["passed"] and (root / "attempts/a/review.json").is_file()

import asyncio
from contextlib import asynccontextmanager

import pytest

from forge_recovery import experiment
from forge_recovery.budget import Ledger
from forge_recovery.common import read_json, write_json


@pytest.fixture
def harness(tmp_path, monkeypatch):
    source = tmp_path / "prepared/inputs"
    (source / "bundle").mkdir(parents=True)
    (source / "bundle/app.js").write_text("minified()")
    (source / "basic").mkdir()
    (source / "basic/animation.piskel").write_text("{}")
    root = tmp_path / "experiment"
    root.mkdir()
    write_json(root / "inputs-publication.json", {"artifact": "test/input:v0"})
    config = {"prepared": str(tmp_path / "prepared"), "experiment_id": "e", "configuration_sha256": "hash",
              "images": {"base": "test", "rea": "test", "checker": "test"}, "model": "test", "task_prompt": "task", "system_prompt": "system", "entity": "test"}
    spec = {"attempt_id": "a", "fixture": "basic", "arm": "baseline", "repetition": 1, "phase": "qualification"}
    class Context:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def record_error(self, *_): pass
        def set_attributes(self, *_): pass
    class Box:
        instances = []
        cancel_close = False
        def __init__(self, workspace, inputs, **_):
            self.workspace = workspace
            self.receipt = workspace.parent / "work.container.json"
            self.container_id = None
            self.closed = False
            self.instances.append(self)
        def start(self):
            self.workspace.mkdir()
            self.container_id = "owned-id"
            write_json(self.receipt, {"status": "running", "id": "owned-id"})
        def resources(self): return {"container_cpu_seconds": 1}
        def close(self):
            self.closed = True
            if self.cancel_close:
                raise asyncio.CancelledError()
            write_json(self.receipt, {"status": "removed", "id": "owned-id"})
            self.container_id = None
    @asynccontextmanager
    async def session(*_):
        yield None
    async def recover(*_):
        return {"completion": "done"}
    monkeypatch.setattr(experiment, "Sandbox", Box)
    monkeypatch.setattr(experiment, "start_conversation", lambda **_: Context())
    monkeypatch.setattr(experiment, "start_turn", lambda **_: Context())
    monkeypatch.setattr(experiment, "span_ids", lambda: {"trace_id": "trace", "span_id": "span"})
    monkeypatch.setattr(experiment, "rea_session", session)
    monkeypatch.setattr(experiment, "recover", recover)
    return config, spec, root, Ledger(tmp_path / "ledger.json"), Box


def test_cancellation_finishes_container_cleanup_and_persists_result(harness, monkeypatch):
    config, spec, root, ledger, box = harness
    async def cancel(*_): raise asyncio.CancelledError()
    monkeypatch.setattr(experiment, "recover", cancel)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(experiment.attempt(config, spec, root, ledger))
    result = read_json(root / "attempts/a/result.json")
    assert result["task_status"] == "cancelled"
    assert result["cleanup_status"] == "complete"
    assert box.instances[0].closed


def test_cancellation_in_final_cleanup_retains_owned_resource(harness):
    config, spec, root, ledger, box = harness
    box.cancel_close = True
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(experiment.attempt(config, spec, root, ledger))
    result = read_json(root / "attempts/a/result.json")
    assert result["task_status"] == "cancelled"
    assert result["cleanup_status"] == "retry_required"
    assert result["cleanup_retry_receipts"]
    assert box.instances[0].container_id == "owned-id"


def test_export_and_upload_failures_preserve_task_result(harness, monkeypatch):
    config, spec, root, ledger, box = harness
    async def export_failure(session, sandbox, root, result):
        result["evidence_export"] = {"status": "failed", "error": "test export failed"}
    def fail(*_): raise OSError("test unavailable")
    monkeypatch.setattr(experiment, "export_evidence", export_failure)
    monkeypatch.setattr(experiment, "evaluate", lambda *_: {"passed": False})
    monkeypatch.setattr(experiment, "readback", fail)
    monkeypatch.setattr(experiment, "upload_attempt", fail)
    result = asyncio.run(experiment.attempt(config, spec, root, ledger))
    assert result["task_status"] == "task_failure"
    assert result["upload_status"] == "failed"
    assert result["evidence_export"]["status"] == "failed"
    assert result["cleanup_status"] == "complete"
    assert read_json(root / "attempts/a/result.json") == result


def test_image_retention_closes_every_resource_after_partial_start(harness):
    config, spec, root, ledger, box = harness
    original_start = box.start
    def fail_second(self):
        self.workspace.parent.mkdir(parents=True, exist_ok=True)
        original_start(self)
        if len(box.instances) == 2:
            raise RuntimeError("startup failed after identity was recorded")
    box.start = fail_second
    with pytest.raises(RuntimeError, match="startup failed"):
        with experiment.retain_images(config, root):
            pytest.fail("must not begin attempts")
    assert len(box.instances) == 2
    assert all(b.closed and b.container_id is None for b in box.instances)

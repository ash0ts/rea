"""Publication preserves the distinction between failed and unavailable checks."""
from types import SimpleNamespace

import pytest

from forge_recovery import telemetry


@pytest.mark.parametrize("checker,expected,available", [(None, None, False), ({"passed": False}, False, True), ({"passed": True}, True, True)])
def test_upload_preserves_checker_availability(tmp_path, monkeypatch, checker, expected, available):
    summary = {}

    class Run:
        id = "attempt"
        url = "https://example.invalid/attempt"

        def __enter__(self):
            self.summary = summary
            return self

        def __exit__(self, *_):
            return False

        def log_artifact(self, artifact):
            return SimpleNamespace(wait=lambda: SimpleNamespace(name="attempt:v0", digest="digest"))

    monkeypatch.setattr(telemetry.wandb, "init", lambda **_: Run())
    monkeypatch.setattr(telemetry.wandb, "Artifact", lambda *_, **__: SimpleNamespace(add_file=lambda *_args, **_kwargs: None))
    result = {"attempt_id": "attempt", "experiment_id": "experiment", "phase": "scored",
              "identity": {}, "task_status": "timeout", "usage": {"input_tokens": 42}}
    if checker is not None:
        result["checker"] = checker
    (tmp_path / "result.json").write_text("{}")
    publication = telemetry.upload_attempt("entity", tmp_path, result)
    assert summary == {"task_status": "timeout", "passed": expected,
                       "checks_available": available, "input_tokens": 42}
    assert publication["artifact"] == "entity/rea-showcase/attempt:v0"

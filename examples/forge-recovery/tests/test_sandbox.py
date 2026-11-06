import json
from types import SimpleNamespace

import pytest

from forge_recovery.sandbox import Sandbox


def test_cleanup_failure_retains_owner_and_can_be_retried(tmp_path, monkeypatch):
    sandbox = Sandbox(tmp_path / "work", tmp_path)
    sandbox.container_id = "owned-id"
    removals = []
    def run(command, **kwargs):
        if command[1] == "inspect":
            return SimpleNamespace(returncode=0, stdout=json.dumps([{"Id": "owned-id", "Config": {"Labels": {"rea-recovery.owner": sandbox.owner}}}]))
        removals.append(command)
        return SimpleNamespace(returncode=1 if len(removals) == 1 else 0, stderr="busy")
    monkeypatch.setattr("forge_recovery.sandbox.subprocess.run", run)
    with pytest.raises(RuntimeError, match="cleanup failed"):
        sandbox.close()
    assert sandbox.container_id == "owned-id"
    sandbox.close()
    assert sandbox.container_id is None
    assert json.loads(sandbox.receipt.read_text())["status"] == "removed"


def test_cleanup_refuses_changed_identity(tmp_path, monkeypatch):
    sandbox = Sandbox(tmp_path / "work", tmp_path)
    sandbox.container_id = "owned-id"
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout=json.dumps([{"Id": "owned-id", "Config": {"Labels": {"rea-recovery.owner": "different"}}}]))
    monkeypatch.setattr("forge_recovery.sandbox.subprocess.run", run)
    with pytest.raises(RuntimeError, match="identity mismatch"):
        sandbox.close()
    assert len(calls) == 1
    assert sandbox.container_id == "owned-id"


@pytest.mark.parametrize("phase", ["start", "execute", "close"])
def test_docker_deadlines_preserve_ownership_and_are_not_command_exits(tmp_path, monkeypatch, phase):
    import subprocess
    from forge_recovery.sandbox import SandboxTransportError
    sandbox = Sandbox(tmp_path / "work", tmp_path)
    if phase != "start":
        sandbox.container_id = "owned-id"
        sandbox.receipt.write_text(json.dumps({"owner": sandbox.owner, "id": "owned-id", "status": "running"}))
    calls = []
    def stalled(command, **kwargs):
        calls.append((command, kwargs["timeout"]))
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])
    monkeypatch.setattr("forge_recovery.sandbox.subprocess.run", stalled)
    with pytest.raises(SandboxTransportError, match="did not respond"):
        if phase == "execute":
            sandbox.execute("pwd", timeout=2)
        else:
            getattr(sandbox, phase)()
    assert calls[0][1] == {"start": 30, "execute": 12, "close": 15}[phase]
    retained = json.loads(sandbox.receipt.read_text())
    assert retained["owner"] == sandbox.owner
    assert retained["status"] == ("starting" if phase == "start" else "running")
    assert sandbox.start_pending if phase == "start" else sandbox.container_id == "owned-id"


def test_candidate_deadline_is_still_a_returned_command_result(tmp_path, monkeypatch):
    sandbox = Sandbox(tmp_path / "work", tmp_path)
    sandbox.container_id = "owned-id"
    result = {"exit_code": 124, "stdout": "", "stderr": "Command timed out", "truncated": False}
    monkeypatch.setattr("forge_recovery.sandbox.subprocess.run", lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(result).encode(), stderr=b""))
    assert sandbox.execute("sleep 100", timeout=1) == result

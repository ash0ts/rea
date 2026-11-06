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

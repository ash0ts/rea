import importlib.util
from pathlib import Path
import subprocess

import pytest


@pytest.mark.parametrize("failure", [None, "base", "rea", "campaign"])
def test_build_images_stay_owned_until_campaign_finishes_and_unwind_on_failure(tmp_path, monkeypatch, failure):
    script = Path(__file__).resolve().parents[1] / "scripts/build_containers.py"
    spec = importlib.util.spec_from_file_location("build_recovery_containers", script)
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    active = []
    closed = []
    executed = []
    class Box:
        def __init__(self, workspace, inputs, image, owner):
            self.image = image
        def start(self): active.append(self.image)
        def close(self):
            active.remove(self.image)
            closed.append(self.image)
    def run(command, **_):
        if command[:2] == ["docker", "build"]:
            role = command[3].split("-")[-1].split(":")[0]
            assert len(active) == ("base", "rea", "checker").index(role)
            executed.append(role)
            if failure == role:
                raise subprocess.CalledProcessError(1, command)
        elif command == ["campaign"]:
            assert len(active) == 3
            executed.append("campaign")
            if failure == "campaign":
                raise subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(build.subprocess, "check_output", lambda *_, **__: str(tmp_path))
    monkeypatch.setattr(build.subprocess, "run", run)
    monkeypatch.setattr(build, "Sandbox", Box)
    if failure:
        with pytest.raises(subprocess.CalledProcessError):
            build.build_and_run(tmp_path, ["campaign"])
    else:
        build.build_and_run(tmp_path, ["campaign"])
    assert not active
    assert len(closed) == {None: 3, "base": 0, "rea": 1, "campaign": 3}[failure]
    if failure in (None, "campaign"):
        assert executed == ["base", "rea", "checker", "campaign"]

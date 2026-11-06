import copy
import importlib.util
import json
from pathlib import Path

import pytest

from forge_recovery.common import digest, read_json, write_json


@pytest.fixture
def rechecker():
    path = Path(__file__).resolve().parents[1] / "notebooks/recheck_preview.py"
    spec = importlib.util.spec_from_file_location("preview_recheck_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def recorded_campaign(tmp_path):
    specs = [{"attempt_id": f"attempt-{i:02}"} for i in range(24)]
    write_json(tmp_path / "experiment.json", {"experiment_id": "frozen", "configuration_sha256": "configuration", "attempts": specs,
        "images": {"checker": "frozen-image"}, "code": {"containers/preview_check.py": "original-checker"}})
    for i, spec in enumerate(specs):
        case = {"decoder": {"exit_code": 0}, "pixels": {"passed": True}, "preview": {"passed": i % 2 == 0}}
        checker = {"passed": i % 2 == 0, "cases": {k: copy.deepcopy(case) for k in ("visible", "heldout")},
            "regressions": {k: {"passed": True} for k in ("malformed", "missing-chunk")}}
        write_json(tmp_path / "attempts" / spec["attempt_id"] / "result.json", {**spec, "configuration_sha256": "configuration",
            "upload_status": "complete", "cleanup_status": "complete", "checker": checker})
    return tmp_path


def test_uniform_recheck_covers_original_successes_and_failures_without_mutation(rechecker, recorded_campaign, monkeypatch):
    root = recorded_campaign
    before = {p: digest(p) for p in root.glob("attempts/*/result.json")}
    calls = []
    def grade(source, destination, image):
        calls.append((source.parents[2].name, source.parent.name))
        assert source.name == "verified-output"
        assert image == "frozen-image"
        return {"preview": {"passed": True, "scrubbing": True, "playback": True, "download": True}}
    monkeypatch.setattr(rechecker, "grade_preview", grade)
    result = rechecker.run(root)
    expected = {(f"attempt-{i:02}", kind) for i in range(24) for kind in ("visible", "heldout")}
    assert len(calls) == 48 and set(calls) == expected
    assert result["complete"] and len(result["attempts"]) == 24
    assert all(row["checker"]["passed"] for row in result["attempts"].values())
    assert {row["original_passed"] for row in result["attempts"].values()} == {True, False}
    assert before == {p: digest(p) for p in before}


def test_recheck_refuses_partial_campaign_before_running_a_checker(rechecker, recorded_campaign, monkeypatch):
    (recorded_campaign / "attempts/attempt-23/result.json").unlink()
    monkeypatch.setattr(rechecker, "grade_preview", lambda *_: pytest.fail("Partial campaign must not be selectively rechecked"))
    with pytest.raises(ValueError, match="Finish all scored"):
        rechecker.run(recorded_campaign)


@pytest.mark.parametrize("change", ["source", "original"])
def test_recheck_refuses_stale_source_or_original_result(rechecker, recorded_campaign, monkeypatch, tmp_path, change):
    monkeypatch.setattr(rechecker, "grade_preview", lambda *_: {"preview": {"passed": True}})
    checker = tmp_path / "checker.py"
    checker.write_bytes(rechecker.CHECKER.read_bytes())
    monkeypatch.setattr(rechecker, "CHECKER", checker)
    rechecker.run(recorded_campaign)
    if change == "source":
        checker.write_text(checker.read_text() + "\n# changed\n")
    else:
        path = recorded_campaign / "attempts/attempt-00/result.json"
        row = read_json(path)
        row["changed"] = True
        write_json(path, row)
    with pytest.raises(ValueError, match="changed"):
        rechecker.run(recorded_campaign)

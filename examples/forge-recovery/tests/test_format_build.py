"""An interrupted build must not overwrite the only retained ownership record."""
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("receipt", ["retained-images.json", "retention/base.container.json"])
def test_existing_build_ownership_stops_before_any_build(tmp_path, monkeypatch, receipt):
    source = Path(__file__).resolve().parents[1] / "format_recovery/build_images.py"
    script = tmp_path / "format_recovery/build_images.py"
    script.parent.mkdir()
    shutil.copy2(source, script)
    record = tmp_path / ".local/format-recovery-build" / receipt
    record.parent.mkdir(parents=True)
    record.write_text('{"owner":"retained-owner","id":"owned-id"}\n')
    before = record.read_bytes()
    def forbidden(*_, **__): pytest.fail("Existing ownership must be checked before Docker build")
    monkeypatch.setattr(subprocess, "run", forbidden)
    with pytest.raises(RuntimeError, match="ownership records"):
        runpy.run_path(str(script))
    assert record.read_bytes() == before

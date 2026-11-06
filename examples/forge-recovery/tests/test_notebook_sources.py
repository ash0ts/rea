import ast
from pathlib import Path

import pytest


@pytest.mark.parametrize("name", ["recover_animation.py", "compare_recovery.py"])
def test_recorded_notebooks_cannot_launch_the_paid_runner(name):
    path = Path(__file__).resolve().parents[1] / "notebooks" / name
    source = path.read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name not in {"openai", "subprocess", "forge_recovery.agent", "forge_recovery.experiment"} for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith(("openai", "subprocess", "forge_recovery"))
    assert ":latest" not in source
    assert 'marimo==0.25.2' in source
    assert 'comparison_ref = ' in source

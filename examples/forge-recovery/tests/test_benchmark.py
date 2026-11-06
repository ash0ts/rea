import json
from pathlib import Path

import pytest
from PIL import Image

from forge_recovery.benchmark import stage_bundle
from forge_recovery.checker import grade
from forge_recovery.common import inventory, verify_inventory, write_json


def test_staging_excludes_embedded_source_maps_and_unminified_code(tmp_path):
    build = tmp_path / "build/js"
    build.mkdir(parents=True)
    selected = build / "piskel-packaged-min-1.js"
    selected.write_text("var a=1;//# sourceMappingURL=code.map")
    (build / "piskel-packaged-1.js").write_text("secret oracle source")
    (build / "piskel-packaged-min-1.js.map").write_text('{"sourcesContent":["secret"]}')
    target = tmp_path / "input"
    stage_bundle(build.parent, target)
    assert (target / selected.name).read_bytes() == selected.read_bytes()
    assert sorted(p.name for p in target.iterdir()) == ["INPUTS.json", selected.name]
    frozen = inventory(target)
    verify_inventory(target, frozen)
    (target / selected.name).write_text("changed")
    with pytest.raises(ValueError, match="Frozen inputs changed"):
        verify_inventory(target, frozen)


@pytest.fixture
def recovery(tmp_path):
    output, expected = tmp_path / "output", tmp_path / "expected"
    output.mkdir()
    expected.mkdir()
    frames = []
    for i, color in enumerate(((255, 0, 0, 255), (0, 255, 0, 128))):
        name = f"frame-{i:03}.png"
        frame = Image.new("RGBA", (3, 2), color)
        frame.save(output / name)
        frame.save(expected / name)
        frames.append(name)
    manifest = {"width": 3, "height": 2, "fps": 8, "hidden_frames": [1], "playback_order": [0], "frames": frames}
    write_json(output / "manifest.json", manifest)
    write_json(expected / "expected.json", {**manifest, "frame_count": 2})
    sheet = Image.new("RGBA", (6, 2))
    for i, name in enumerate(frames):
        with Image.open(output / name) as frame:
            sheet.paste(frame, (i * 3, 0))
    sheet.save(output / "spritesheet.png")
    return output, expected, manifest


def test_checker_accepts_independent_pixels(recovery):
    output, expected, _ = recovery
    assert grade(output, expected)["passed"]


def test_checker_detects_rgb_difference_even_when_alpha_matches(recovery):
    output, expected, _ = recovery
    Image.new("RGBA", (3, 2), (0, 0, 255, 255)).save(output / "frame-000.png")
    assert not grade(output, expected)["criteria"]["pixels"]


def test_checker_rejects_frame_reordering_and_hidden_frame_loss(recovery):
    output, expected, manifest = recovery
    manifest["frames"].reverse()
    manifest["hidden_frames"] = []
    write_json(output / "manifest.json", manifest)
    result = grade(output, expected)
    assert not result["criteria"]["frame_order"]
    assert not result["criteria"]["hidden_frames"]


@pytest.mark.parametrize("corruption", ["malformed", "missing_frame", "missing_manifest", "path_escape"])
def test_incomplete_outputs_are_failures(recovery, corruption):
    output, expected, manifest = recovery
    if corruption == "malformed":
        (output / "manifest.json").write_text("{")
    elif corruption == "missing_frame":
        (output / "frame-001.png").unlink()
    elif corruption == "missing_manifest":
        (output / "manifest.json").unlink()
    else:
        manifest["frames"][0] = "../expected/frame-000.png"
        write_json(output / "manifest.json", manifest)
    assert not grade(output, expected)["passed"]

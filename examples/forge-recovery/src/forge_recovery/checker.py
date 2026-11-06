from __future__ import annotations

import json
import hashlib
from pathlib import Path

from PIL import Image, ImageChops

from .common import read_json


def rgba_equal(left: Path, right: Path) -> bool:
    with Image.open(left) as a, Image.open(right) as b:
        a, b = a.convert("RGBA"), b.convert("RGBA")
        return a.size == b.size and ImageChops.difference(a, b).getbbox(alpha_only=False) is None


def grade(output: Path, expected: Path) -> dict:
    criteria = {key: False for key in ("pixels", "frame_order", "dimensions", "fps", "hidden_frames", "sprite_sheet")}
    reasons = []
    try:
        actual = read_json(output / "manifest.json")
        truth = read_json(expected / "expected.json")
        criteria["dimensions"] = (actual.get("width"), actual.get("height")) == (truth["width"], truth["height"])
        criteria["fps"] = actual.get("fps") == truth["fps"]
        criteria["hidden_frames"] = actual.get("hidden_frames") == truth["hidden_frames"] and actual.get("playback_order") == truth["playback_order"]
        names = actual.get("frames", [])
        if not isinstance(names, list) or len(names) != truth["frame_count"]:
            raise ValueError("Wrong frame count")
        paths = []
        for name in names:
            if not isinstance(name, str) or Path(name).name != name or not name.endswith(".png"):
                raise ValueError("Frame names must be PNG basenames")
            path = output / name
            if path.is_symlink():
                raise ValueError("Output frames must be regular files")
            paths.append(path)
        matches = [rgba_equal(path, expected / f"frame-{i:03}.png") for i, path in enumerate(paths)]
        criteria["frame_order"] = all(matches)
        def pixels(path):
            with Image.open(path) as image:
                return hashlib.sha256(image.convert("RGBA").tobytes()).hexdigest()
        criteria["pixels"] = sorted(pixels(path) for path in paths) == sorted(pixels(expected / f"frame-{i:03}.png") for i in range(len(paths)))
        sheet = Image.new("RGBA", (truth["width"] * len(paths), truth["height"]))
        for i in range(len(paths)):
            with Image.open(expected / f"frame-{i:03}.png") as frame:
                sheet.paste(frame.convert("RGBA"), (i * truth["width"], 0))
        with Image.open(output / "spritesheet.png") as candidate:
            candidate = candidate.convert("RGBA")
            criteria["sprite_sheet"] = candidate.size == sheet.size and ImageChops.difference(candidate, sheet).getbbox(alpha_only=False) is None
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
        reasons.append(f"{type(error).__name__}: {error}")
    return {"passed": all(criteria.values()), "criteria": criteria, "reasons": reasons}

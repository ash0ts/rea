"""Run submitted code in new containers; expected pixels remain on the controller."""
from __future__ import annotations

import json
import shutil
import stat
import time
from pathlib import Path

from .checker import grade
from .common import read_json, write_json
from .sandbox import Sandbox


def copy_regular_tree(source: Path, destination: Path) -> None:
    files = []
    total = 0
    for path in source.rglob("*"):
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            continue
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"Submission contains a nonregular file: {path.relative_to(source)}")
        total += info.st_size
        if total > 100 * 1024 * 1024:
            raise ValueError("Submission exceeds the 100 MiB artifact limit")
        files.append(path)
    destination.mkdir(parents=True, exist_ok=False)
    for path in files:
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def invalid_samples(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True)
    (destination / "malformed.piskel").write_text("{broken")
    value = read_json(source)
    layer = json.loads(value["piskel"]["layers"][0])
    if "chunks" in layer:
        layer["chunks"] = []
    else:
        layer.pop("base64PNG", None)
    value["piskel"]["layers"][0] = json.dumps(layer)
    write_json(destination / "missing-chunk.piskel", value)


def stage_decoder(candidate: Path, work: Path) -> None:
    """Fresh output proves the submitted standalone program generated it."""
    work.mkdir(parents=True)
    decoder = candidate / "decode.py"
    if decoder.is_file() and not decoder.is_symlink():
        shutil.copyfile(decoder, work / "decode.py")


def evaluate(candidate: Path, oracle: Path, root: Path, images: dict, deadline: float | None = None) -> dict:
    def run(box, command, timeout):
        remaining = deadline - time.monotonic() - 10 if deadline else timeout
        if remaining <= 0:
            raise TimeoutError("Attempt execution deadline reached during checking")
        return box.execute(command, timeout=min(timeout, remaining))
    result = {"cases": {}, "regressions": {}, "resources": []}
    for kind in ("visible", "heldout"):
        folder = root / kind
        inputs = folder / "input"
        inputs.mkdir(parents=True)
        shutil.copyfile(oracle / kind / "animation.piskel", inputs / "animation.piskel")
        work = folder / "work"
        stage_decoder(candidate, work)
        with Sandbox(work, inputs, image=images["base"]) as box:
            executed = run(box, "python decode.py /input/animation.piskel /work/output", 45)
            result["resources"].append(box.resources())
        output = folder / "verified-output"
        if (work / "output").is_dir():
            copy_regular_tree(work / "output", output)
        pixels = grade(output, oracle / kind)
        preview = {"passed": False, "errors": ["Decoder or pixel check failed"]}
        if executed["exit_code"] == 0 and pixels["passed"]:
            browser_work = folder / "browser"
            browser_work.mkdir()
            copy_regular_tree(output, browser_work / "output")
            with Sandbox(browser_work, inputs, image=images["checker"]) as box:
                checked = run(box, "python /opt/recovery/preview_check.py", 60)
                result["resources"].append(box.resources())
            try:
                preview = json.loads(checked["stdout"])
            except (ValueError, KeyError):
                preview = {"passed": False, "errors": [checked]}
        result["cases"][kind] = {"decoder": executed, "pixels": pixels, "preview": preview}
    bad_inputs = root / "invalid-input"
    invalid_samples(oracle / "heldout/animation.piskel", bad_inputs)
    work = root / "invalid-work"
    stage_decoder(candidate, work)
    valid_inputs_decoded = all(c["decoder"]["exit_code"] == 0 for c in result["cases"].values())
    with Sandbox(work, bad_inputs, image=images["base"]) as box:
        for name in ("malformed", "missing-chunk"):
            checked = run(box, f"python decode.py /input/{name}.piskel /work/{name}-output", 15)
            result["regressions"][name] = {
                "passed": valid_inputs_decoded and checked["exit_code"] not in (0, 124, 137) and bool(checked["stderr"] or checked["stdout"]),
                "valid_input_control_passed": valid_inputs_decoded,
                "execution": checked,
            }
        result["resources"].append(box.resources())
    result["passed"] = all(c["decoder"]["exit_code"] == 0 and c["pixels"]["passed"] and c["preview"]["passed"] for c in result["cases"].values()) and all(c["passed"] for c in result["regressions"].values())
    return result

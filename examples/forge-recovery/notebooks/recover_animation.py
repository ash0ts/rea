# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "marimo==0.25.2",
#     "wandb==0.31.0",
#     "pillow==13.0.0",
# ]
# ///

import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="Recover the animation")


@app.cell
def _():
    import io
    import json
    from pathlib import Path
    import marimo as mo
    import wandb
    from PIL import Image, ImageChops

    return Image, ImageChops, Path, io, json, mo, wandb


@app.cell
def _(mo):
    mo.md("""
    # Recover the animation
    A source-withheld Piskel exercise: inspect a shipped minified bundle, recover a
    saved animation, then test the submitted decoder on an unseen variant.

    **The pictures are checked outputs.** Original pixels come from pinned Piskel;
    recovered pixels come from the submitted decoder in a separate container.
    Controls here read frozen artifacts and never launch inference or execute the
    submitted decoder. Piskel is a known public format; prior model familiarity is a limitation.
    """)
    return


@app.cell
def _(Path, json, mo, wandb):
    # Replaced with a committed immutable version by publish_comparison.py.
    comparison_ref = "UNPUBLISHED"
    mo.stop(comparison_ref == "UNPUBLISHED", mo.callout("Recorded comparison has not been published yet.", kind="warn"))
    api = wandb.Api()
    comparison_root = Path(api.artifact(comparison_ref).download())
    comparison = json.loads((comparison_root / "comparison.json").read_text())
    attempts = comparison["summary"]["attempts"]
    reference_root = Path(api.artifact(comparison["inputs"]["artifact"]).download())
    return api, attempts, reference_root


@app.cell
def _(attempts, mo):
    rea_rows = [r for r in attempts if r["arm"] == "rea"]
    mo.stop(not rea_rows, mo.callout("No scored attempts recorded.", kind="warn"))
    first_success = next((r for r in rea_rows if r.get("checker", {}).get("passed")), None)
    initial = first_success or rea_rows[0]
    choices = {f"{r['fixture']} · repetition {r['repetition']} · {r['task_status']}": r["attempt_id"] for r in rea_rows}
    choose_attempt = mo.ui.dropdown(choices, value=next(k for k, v in choices.items() if v == initial["attempt_id"]), label="Paired attempt")
    mo.vstack([choose_attempt, mo.md("Default: first successful REA attempt in manifest order." if first_success else "No REA attempt passed every check; showing the first recorded failure explicitly.")])
    return (choose_attempt,)


@app.cell
def _(Path, api, attempts, choose_attempt, mo):
    selected = next(r for r in attempts if r["attempt_id"] == choose_attempt.value)
    paired = next((r for r in attempts if r["fixture"] == selected["fixture"] and r["repetition"] == selected["repetition"] and r["arm"] == "baseline"), None)
    choose_case = mo.ui.radio(["visible", "heldout"], value="heldout", label="Independent check input", inline=True)
    recovered_roots = {}
    for _row in [selected, paired]:
        if _row and _row.get("publication"):
            recovered_roots[_row["arm"]] = Path(api.artifact(_row["publication"]["artifact"]).download())
    mo.vstack([choose_case, mo.md(f"**{selected['fixture']}**, repetition **{selected['repetition']}**. REA: **{selected['task_status']}**; baseline: **{paired['task_status'] if paired else 'unavailable'}**.")])
    return choose_case, paired, recovered_roots, selected


@app.cell
def _(choose_case, json, mo, reference_root, selected):
    original = reference_root / "oracle" / selected["fixture"] / choose_case.value
    expected = json.loads((original / "expected.json").read_text())
    frame = mo.ui.slider(0, expected["frame_count"] - 1, step=1, value=0, show_value=True, label="Frame (includes hidden frames)")
    layer = mo.ui.dropdown({f"Layer {i} · opacity {opacity}": i for i, opacity in enumerate(expected["layer_opacities"])}, value=f"Layer 0 · opacity {expected['layer_opacities'][0]}", label="Original layer")
    mo.hstack([frame, layer], justify="start", gap=2)
    return expected, frame, layer, original


@app.cell
def _(
    Image,
    ImageChops,
    Path,
    choose_case,
    expected,
    frame,
    io,
    json,
    layer,
    mo,
    original,
    recovered_roots,
):
    def display_image(path):
        return mo.image(Image.open(path).resize((expected["width"] * 10, expected["height"] * 10), Image.Resampling.NEAREST))

    def animation(folder, names, order, fps):
        buffer = io.BytesIO()
        frames = [Image.open(folder / names[i]).convert("RGBA").resize((expected["width"] * 10, expected["height"] * 10), Image.Resampling.NEAREST) for i in order]
        frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:], duration=1000 / fps, loop=0, disposal=2)
        return mo.image(buffer.getvalue(), alt="Recorded animation playback")

    original_names = [f"frame-{i:03}.png" for i in range(expected["frame_count"])]
    cards = [mo.vstack([mo.md("### Original Piskel renderer"), animation(original, original_names, expected["playback_order"], expected["fps"]), display_image(original / original_names[frame.value])])]
    differences = []
    for arm in ("rea", "baseline"):
        _folder = recovered_roots.get(arm)
        _folder = _folder / "checks" / choose_case.value / "verified-output" if _folder else None
        if _folder is None or not (_folder / "manifest.json").exists():
            cards.append(mo.callout(f"{arm}: recovered output unavailable", kind="warn"))
            continue
        try:
            _metadata = json.loads((_folder / "manifest.json").read_text())
            if len(_metadata["frames"]) != expected["frame_count"] or any(not isinstance(name, str) or Path(name).name != name for name in _metadata["frames"]):
                raise ValueError("Output frame names/count are invalid")
            if not _metadata["playback_order"] or any(not isinstance(i, int) or not 0 <= i < expected["frame_count"] for i in _metadata["playback_order"]) or not 0 < _metadata["fps"] < float("inf"):
                raise ValueError("Output playback metadata is invalid")
            _candidate = _folder / _metadata["frames"][frame.value]
            _left = Image.open(original / original_names[frame.value]).convert("RGBA")
            _right = Image.open(_candidate).convert("RGBA")
            if _left.size == _right.size:
                _diff = ImageChops.difference(_left, _right)
                _changed = sum(a != b for a, b in zip(_left.getdata(), _right.getdata()))
                differences.append(mo.vstack([mo.md(f"**{arm} pixel difference:** {_changed} changed RGBA pixels"), mo.image(_diff.convert("RGB").resize((_left.width * 10, _left.height * 10), Image.Resampling.NEAREST))]))
            cards.append(mo.vstack([mo.md(f"### {arm.upper()} recovery"), animation(_folder, _metadata["frames"], _metadata["playback_order"], _metadata["fps"]), display_image(_candidate)]))
        except (OSError, ValueError, KeyError, IndexError) as _error:
            cards.append(mo.callout(f"{arm}: output could not be rendered: {_error}", kind="warn"))
    mo.vstack([mo.hstack(cards, wrap=True, align="start"), mo.md(f"{expected['width']} × {expected['height']} · {expected['fps']} FPS · hidden indices: {expected['hidden_frames']} · GIF playback is a viewing aid; the checker uses exact PNG pixels and browser-clock timing."), mo.hstack(differences, wrap=True), mo.md("### Inspect an original layer"), display_image(original / f"layer-{layer.value}-{frame.value:03}.png")])
    return


@app.cell
def _(mo, paired, selected):
    links = []
    for _row in [selected, paired]:
        if _row:
            _publication = _row.get("publication", {})
            links.append(mo.md(f"**{_row['arm']}** · [Agent Lens]({_row['lens_url']}) · [Run and versioned artifacts]({_publication.get('run_url', _row['lens_url'])})\n\nAttempt: `{_row['attempt_id']}` · Evidence export: `{_row.get('evidence_export', {}).get('status', 'unavailable')}`"))
    mo.vstack([mo.md("## Follow the evidence"), *links, mo.accordion({"Independent checker details": mo.json({"rea": selected.get("checker"), "baseline": paired.get("checker") if paired else None})})])
    return


if __name__ == "__main__":
    app.run()

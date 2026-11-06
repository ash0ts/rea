# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "marimo==0.25.1",
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
    from importlib.metadata import version as _version

    for _package, _pin in {"marimo": "0.25.1", "wandb": "0.31.0", "pillow": "13.0.0"}.items():
        if _version(_package) != _pin:
            raise RuntimeError(f"This notebook requires {_package}=={_pin}; runtime has {_version(_package)}. Restore the saved dependency pins before running it.")

    return Image, ImageChops, Path, io, json, mo, wandb


@app.cell
def _(mo):
    mo.md("""
    # Recover the animation
    A source-withheld Piskel exercise: inspect a shipped minified bundle, recover a
    saved animation, then test the submitted decoder on an unseen variant.

    The subject is an original **Signal explorer** robot: it walks, changes color,
    and leaves a magenta frame marker. The fixture families vary translucent layers,
    geometry, image-chunk ordering, hidden frames, and legacy storage. Switch between
    the six-frame input and the unseen nine-frame variant to inspect whether the
    submitted program recovered reusable behavior.

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
    mo.md(f"Score basis: {comparison['summary'].get('score_basis', 'Original independent checker')}. Original records and any uniform correction are available in the comparison notebook.")
    reference_root = Path(api.artifact(comparison["inputs"]["artifact"]).download())
    return api, attempts, reference_root


@app.cell
def _(attempts, mo):
    rea_rows = [r for r in attempts if r["arm"] == "rea"]
    mo.stop(not rea_rows, mo.callout("No scored attempts recorded.", kind="warn"))
    first_success = next((r for r in rea_rows if r.get("checker", {}).get("passed")), None)
    initial = first_success or rea_rows[0]
    choices = {f"{r['fixture']} · repetition {r['repetition']} · checks {r.get('checker', {}).get('passed', 'unavailable')} · {r['task_status']}": r["attempt_id"] for r in rea_rows}
    choose_attempt = mo.ui.dropdown(choices, value=next(k for k, v in choices.items() if v == initial["attempt_id"]), label="Paired attempt")
    mo.vstack([choose_attempt, mo.md("Default: first successful REA attempt in manifest order." if first_success else "No REA attempt passed every check; showing the first recorded failure explicitly.")])
    return (choose_attempt,)


@app.cell
def _(Path, api, attempts, choose_attempt, mo):
    selected = next(r for r in attempts if r["attempt_id"] == choose_attempt.value)
    paired = next((r for r in attempts if r["fixture"] == selected["fixture"] and r["repetition"] == selected["repetition"] and r["arm"] == "baseline"), None)
    choose_case = mo.ui.radio(["visible", "heldout"], value="heldout", label="Independent check input", inline=True)
    recovered_roots = {}
    artifact_urls = {}
    for _row in [selected, paired]:
        if _row and _row.get("publication"):
            _artifact = api.artifact(_row["publication"]["artifact"])
            recovered_roots[_row["arm"]] = Path(_artifact.download())
            artifact_urls[_row["arm"]] = _artifact.url
    mo.vstack([choose_case, mo.md(f"**{selected['fixture']}**, repetition **{selected['repetition']}**. REA: **{selected['task_status']}**; baseline: **{paired['task_status'] if paired else 'unavailable'}**.")])
    return artifact_urls, choose_case, paired, recovered_roots, selected


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
        frames[0].save(buffer, format="PNG", save_all=True, append_images=frames[1:], duration=1000 / fps, loop=0, disposal=0, blend=0)
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
                _changed = sum(a != b for a, b in zip(_left.get_flattened_data(), _right.get_flattened_data()))
                _mask = Image.new("RGB", _left.size)
                _mask.putdata([(225, 29, 72) if any(pixel) else (241, 245, 249) for pixel in _diff.get_flattened_data()])
                differences.append(mo.vstack([mo.md(f"**{arm} pixel difference:** {_changed} changed RGBA pixels (pink includes alpha-only changes)"), mo.image(_mask.resize((_left.width * 10, _left.height * 10), Image.Resampling.NEAREST))]))
            cards.append(mo.vstack([mo.md(f"### {arm.upper()} recovery"), animation(_folder, _metadata["frames"], _metadata["playback_order"], _metadata["fps"]), display_image(_candidate)]))
        except (OSError, ValueError, KeyError, IndexError) as _error:
            cards.append(mo.callout(f"{arm}: output could not be rendered: {_error}", kind="warn"))
    mo.vstack([mo.hstack(cards, wrap=True, align="start"), mo.md(f"{expected['width']} × {expected['height']} · {expected['fps']} FPS · hidden indices: {expected['hidden_frames']} · Animated PNG playback is a viewing aid; the checker uses exact PNG pixels and browser-clock timing."), mo.hstack(differences, wrap=True), mo.md("### Inspect an original layer"), display_image(original / f"layer-{layer.value}-{frame.value:03}.png")])
    return


@app.cell
def _(artifact_urls, json, mo, paired, recovered_roots, selected):
    links = []
    evidence_rows = []
    tool_steps = []
    for _row in [selected, paired]:
        if _row:
            _publication = _row.get("publication", {})
            links.append(mo.md(f"**{_row['arm']}** · [Agent Lens]({_row['lens_url']}) · [Run]({_publication.get('run_url', _row['lens_url'])}) · [Immutable artifact and complete Evidence]({artifact_urls.get(_row['arm'], _row['lens_url'])})\n\nAttempt: `{_row['attempt_id']}` · Artifact: `{_publication.get('artifact', 'unavailable')}` · Evidence export: `{_row.get('evidence_export', {}).get('status', 'unavailable')}`"))
            _root = recovered_roots.get(_row["arm"])
            if _root and (_root / "events.json").is_file():
                for _event in json.loads((_root / "events.json").read_text()):
                    if _event["kind"] == "tool":
                        _url = f"{_row['lens_url']}?chatTab=spans&convTurn=1&chatTrace={_event['trace_id']}&span={_event['span_id']}"
                        tool_steps.append({"arm": _row["arm"], "tool": _event["tool"], "tool-call ID": _event["tool_call_id"], "step": mo.md(f"[Open span]({_url})")})
            if _root and (_root / "evidence/bundle.json").is_file():
                _bundle = json.loads((_root / "evidence/bundle.json").read_text())
                for _record in _bundle["records"]:
                    evidence_rows.append({"arm": _row["arm"], **{_key: _record.get(_key) for _key in ("evidence_id", "operation", "provider", "confidence", "authority", "limitations", "evidence_links")}})
    mo.vstack([mo.md("## Follow the evidence"), *links, mo.ui.table(tool_steps, selection=None, page_size=10), mo.accordion({"Canonical Evidence record summaries": mo.json(evidence_rows), "Independent checker details": mo.json({"rea": selected.get("checker"), "baseline": paired.get("checker") if paired else None})})])
    return


if __name__ == "__main__":
    app.run()

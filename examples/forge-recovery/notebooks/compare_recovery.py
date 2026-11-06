# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "marimo==0.25.1",
#     "wandb==0.31.0",
# ]
# ///
import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="What did REA change?")


@app.cell
def _():
    import json
    from pathlib import Path
    import marimo as mo
    import wandb
    from importlib.metadata import version as _version
    for _package, _pin in {"marimo": "0.25.1", "wandb": "0.31.0"}.items():
        if _version(_package) != _pin:
            raise RuntimeError(f"This notebook requires {_package}=={_pin}; runtime has {_version(_package)}. Restore the saved dependency pins before running it.")
    return Path, json, mo, wandb


@app.cell
def _(mo):
    mo.md("""
    # What did REA change?
    Six Piskel fixture families, two arms, two repetitions: **24 planned scored attempts**.
    Both arms use the same model, prompt, ordinary tools and limits. Treatment adds
    REA's JavaScript analysis and retained Evidence through a persistent MCP session.

    This is a small source-withheld exercise, not evidence of general superiority or
    discovery of a previously unknown format. Repetitions are paired observations of
    the same six cases. Missing measurements stay unavailable; failures stay in the denominator.
    These controls load recorded artifacts only and never launch inference.
    """)
    return


@app.cell
def _(Path, json, mo, wandb):
    comparison_ref = "UNPUBLISHED"
    mo.stop(comparison_ref == "UNPUBLISHED", mo.callout("Recorded comparison has not been published yet.", kind="warn"))
    api = wandb.Api()
    artifact_root = Path(api.artifact(comparison_ref).download())
    data = json.loads((artifact_root / "comparison.json").read_text())
    summary = data["summary"]
    rows = summary["attempts"]
    mo.md(f"**{summary['recorded_scored']} / 24 recorded** · configuration `{summary['configuration_sha256']}` · immutable source `{comparison_ref}`\n\nScore basis: {summary.get('score_basis', 'Original independent checker')}. Task status and resource measurements remain the original recorded outcomes.")
    return data, rows, summary


@app.cell
def _(mo, rows, summary):
    outcome_rows = [{"arm": arm, "passed all checks": summary["arms"][arm]["passed"], "recorded": summary["arms"][arm]["recorded"], "planned": 12, "status counts": str(summary["arms"][arm]["statuses"])} for arm in ("baseline", "rea")]
    paired_rows = []
    for _family in ("basic", "opacity", "non_square", "chunks", "hidden", "legacy"):
        for _rep in (1, 2):
            _pair = {r["arm"]: r for r in rows if r["fixture"] == _family and r["repetition"] == _rep}
            _record = {"case": _family, "repetition": _rep}
            for _arm in ("baseline", "rea"):
                _row = _pair.get(_arm)
                _record[_arm] = _row["task_status"] if _row else "not recorded"
                _record[f"{_arm} passed all checks"] = _row.get("checker", {}).get("passed") if _row else None
                _record[f"{_arm} tokens"] = (_row["usage"]["input_tokens"] + _row["usage"]["output_tokens"]) if _row and _row.get("usage", {}).get("unknown_usage_requests") == 0 else None
                _record[f"{_arm} seconds"] = round(_row["agent_elapsed_seconds"], 2) if _row and "agent_elapsed_seconds" in _row else None
                _record[f"{_arm} USD estimate/reservation"] = round(_row["usage"]["reserved_or_estimated_usd"], 4) if _row and "usage" in _row else None
            paired_rows.append(_record)
    mo.vstack([mo.md("## Paired outcomes"), mo.ui.table(outcome_rows, selection=None), mo.ui.table(paired_rows, selection=None, page_size=12), mo.md("Tokens include full repeated context and tool schemas. USD uses uncached rates; uncertain calls retain their pre-request reservation. Seconds measure the complete agent phase, including REA and finalization; cleanup can extend beyond the execution deadline. Comparing resource use only among successes would omit failed work; the table retains every recorded attempt.")])
    return


@app.cell
def _(mo, rows):
    criterion_rows = []
    for _row in rows:
        for _kind in ("visible", "heldout"):
            _checks = _row.get("checker", {}).get("cases", {}).get(_kind, {})
            criterion_rows.append({"case": _row["fixture"], "arm": _row["arm"], "repetition": _row["repetition"], "input": _kind,
                **{key: _checks.get("pixels", {}).get("criteria", {}).get(key) for key in ("pixels", "frame_order", "dimensions", "fps", "hidden_frames", "sprite_sheet")},
                "preview": _checks.get("preview", {}).get("passed"), "status": _row["task_status"]})
    mo.vstack([mo.md("## Which behavior was recovered?"), mo.md("`true` passes, `false` fails, and blank is unavailable. Pixels and frame ordering are separate criteria. Preview covers scrubbing, ordered playback at the recorded FPS, and download."), mo.ui.table(criterion_rows, selection=None, page_size=24)])
    return


@app.cell
def _(data, mo, rows):
    navigation = [{"attempt": r["attempt_id"], "status": r["task_status"], "Agent Lens": mo.md(f"[Open conversation]({r['lens_url']})"), "Run / artifacts": mo.md(f"[Open run]({r.get('publication', {}).get('run_url', r['lens_url'])})"),
        "agent CPU seconds": r.get("agent_resources", {}).get("container_cpu_seconds"),
        "agent peak MiB": round(r["agent_resources"]["container_peak_memory_bytes"] / 1048576, 2) if r.get("agent_resources", {}).get("container_peak_memory_bytes") is not None else None,
        "REA returned tool calls": (data.get("tool_usage", {}).get(r["attempt_id"]) or {}).get("rea_returned_calls"),
        "all returned tool calls": (data.get("tool_usage", {}).get(r["attempt_id"]) or {}).get("returned_calls"),
        "upload": r.get("upload_status"), "Evidence export": r.get("evidence_export", {}).get("status")} for r in rows]
    choose_failure = mo.ui.dropdown({r["attempt_id"]: r["attempt_id"] for r in rows}, value=rows[0]["attempt_id"] if rows else None, label="Inspect one attempt")
    mo.vstack([mo.md("## Every attempt, including failures"), mo.md("Tool counts come from returned tool-call events, including returned errors. Interrupted calls may appear only in Agent Lens. Zero REA calls means the treatment agent used its ordinary tools without invoking REA; blank means the event log was unavailable."), mo.ui.table(navigation, selection=None, page_size=24), choose_failure])
    return choose_failure,


@app.cell
def _(choose_failure, mo, rows):
    selected_result = next((r for r in rows if r["attempt_id"] == choose_failure.value), None)
    mo.json(selected_result)
    return


@app.cell
def _(data, mo):
    def _recorded_json(value):
        return mo.json(value) if value is not None else mo.md("Not recorded in this artifact.")

    mo.vstack([mo.md("## Limits on interpretation"), mo.md("No replacement retries of scored attempts. Qualification uses separate artwork and is excluded from the scored denominator. REA availability is the treatment; actual use can be inspected in each conversation. Remote model CPU and memory are unavailable. Local peak memory covers the container process family, while controller peak memory is a process-lifetime high-water mark. Each attempt starts a fresh container and analysis session; host filesystem and image caches were not reset. The local host was shared; background contention was not measured. Six cases and two repetitions cannot establish population-level gains."), mo.accordion({"Original checker records": _recorded_json(data.get("original_summary")), "Uniform preview recheck": _recorded_json(data.get("preview_recheck")), "Infrastructure events": mo.json(data.get("infrastructure_events", [])), "Frozen controller source": _recorded_json(data.get("frozen_controller_source")), "Frozen execution ledger": mo.json(data["ledger"]), "Qualification gate": mo.json(data["qualification"]), "Qualification attempts": mo.json(data["qualification_attempts"]), "Earlier qualification failures (original records)": mo.json(data["prior_qualification"]), "Cleanup reconciliations": mo.json(data["cleanup_reconciliations"]), "Artifact integrity readback": mo.json(data.get("artifact_readbacks", [])), "Provenance": mo.json(data["inputs"])})])
    return


if __name__ == "__main__":
    app.run()

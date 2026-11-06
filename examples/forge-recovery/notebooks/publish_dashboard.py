"""Publish native Forge views from recorded results, without launching an agent."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import netrc
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def read(path: Path):
    return json.loads(path.read_text())


def write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(root: Path) -> dict:
    experiment = read(root / "experiment.json")
    comparison = root / "comparison-publication.json"
    final = comparison.exists()
    if final:
        data = read(root / "comparison/comparison.json")
        rows = data["summary"]["attempts"]
        basis = data["summary"]["score_basis"]
        source = read(comparison)
        source["comparison_sha256"] = sha(root / "comparison/comparison.json")
        if len(rows) != 24 or any(r.get("cleanup_status") != "complete" or r.get("upload_status") != "complete" for r in rows):
            raise ValueError("Final dashboard requires 24 uploaded, cleaned-up attempts")
    else:
        rows = [read(p) for spec in experiment["attempts"]
                if (p := root / "attempts" / spec["attempt_id"] / "result.json").exists()]
        basis = "Provisional original checks; uniform corrected preview verification pending"
        source = {"original_result_sha256": {r["attempt_id"]: sha(root / "attempts" / r["attempt_id"] / "result.json") for r in rows}}
    expected = {r["attempt_id"] for r in experiment["attempts"]}
    if len({r["attempt_id"] for r in rows}) != len(rows) or any(r["attempt_id"] not in expected or r["configuration_sha256"] != experiment["configuration_sha256"] for r in rows):
        raise ValueError("Dashboard records differ from the frozen campaign")
    usage = {}
    for row in rows:
        events = root / "attempts" / row["attempt_id"] / "events.json"
        if events.exists():
            counts = Counter(e["tool"] for e in read(events) if e["kind"] == "tool")
            usage[row["attempt_id"]] = {"returned_calls": sum(counts.values()),
                "rea_returned_calls": sum(v for k, v in counts.items() if k != "execute")}
    value = {"experiment_id": experiment["experiment_id"], "entity": experiment["entity"], "project": experiment["project"],
        "configuration_sha256": experiment["configuration_sha256"], "final": final,
        "score_basis": basis, "planned": experiment["attempts"], "attempts": rows,
        "source": source, "tool_usage": usage}
    value["snapshot_id"] = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]
    return value


def measurements(row: dict, usage: dict) -> dict:
    model_usage = row.get("usage") or {}
    resources = row.get("agent_resources") or {}
    checker = row.get("checker") or {}
    result = {"recorded_attempt": 1, "task_status": row["task_status"],
        "checks_available": int("passed" in checker),
        "passed_all_checks": int(checker["passed"]) if "passed" in checker else None,
        "task_tokens": model_usage.get("input_tokens", 0) + model_usage.get("output_tokens", 0)
            if model_usage and model_usage.get("unknown_usage_requests") == 0 else None,
        "agent_seconds": row.get("agent_elapsed_seconds"),
        "cost_estimate_or_reservation_usd": model_usage.get("reserved_or_estimated_usd"),
        "agent_cpu_seconds": resources.get("container_cpu_seconds"),
        "agent_peak_mib": resources["container_peak_memory_bytes"] / 1048576 if resources.get("container_peak_memory_bytes") is not None else None,
        "rea_returned_calls": usage.get("rea_returned_calls"),
        "agent_lens_url": row.get("lens_url"),
        "source_artifact": (row.get("publication") or {}).get("artifact"),
        "cleanup_status": row.get("cleanup_status"), "upload_status": row.get("upload_status")}
    for kind in ("visible", "heldout"):
        case = checker.get("cases", {}).get(kind, {})
        result.update({f"{kind}/{k}": int(v) if isinstance(v, bool) else None for k, v in case.get("pixels", {}).get("criteria", {}).items()})
        result.update({f"{kind}/preview_{k}": int(case.get("preview", {})[k]) if isinstance(case.get("preview", {}).get(k), bool) else None for k in ("scrubbing", "playback", "download")})
    return result


def navigation(value: dict) -> str:
    rows = {r["attempt_id"]: r for r in value["attempts"]}
    lines = ["| Case | Arm | Repetition | Task status | Check result | Evidence |", "|---|---|---:|---|---|---|"]
    for spec in value["planned"]:
        row = rows.get(spec["attempt_id"])
        checked = (row.get("checker") or {}).get("passed") if row else None
        status = row["task_status"] if row else "Not run"
        result = "Pass" if checked is True else "Fail" if checked is False else "Unavailable"
        links = f"[Agent Lens]({row['lens_url']}) · [Run / artifacts]({row['publication']['run_url']})" if row and row.get("publication") else "—"
        lines.append(f"| {spec['fixture']} | {spec['arm']} | {spec['repetition']} | {status} | {result} | {links} |")
    return "\n".join(lines)


def forge_url(url: str, entity: str, project: str) -> str:
    parsed = urlsplit(url)
    # The pinned Workspace SDK drops the application base path when composing
    # links. Keep its original URL for API readback; expose Forge's routed URL.
    if parsed.hostname == "wandb.ai":
        return urlunsplit(("https", "forge.coreweave.com", "/wandb" + parsed.path, parsed.query, parsed.fragment))
    if parsed.hostname == "forge.coreweave.com" and not (parsed.path == f"/wandb/{entity}/{project}" or parsed.path.startswith(f"/wandb/{entity}/{project}/")):
        return urlunsplit((parsed.scheme, parsed.netloc, "/wandb" + parsed.path, parsed.query, parsed.fragment))
    return url


def publish(root: Path) -> dict:
    import wandb
    import wandb_workspaces.reports.v2 as wr
    import wandb_workspaces.workspaces as ws
    from wandb_workspaces import expr

    value = snapshot(root)
    destination = root / "dashboards" / value["snapshot_id"]
    receipt = destination / "publication.json"
    if receipt.exists():
        return read(receipt)
    if (destination / "publishing.json").exists():
        raise ValueError(f"Inspect the incomplete publication and saved resource IDs at {destination} before retrying")
    key = os.environ.get("WANDB_API_KEY")
    if not key:
        auth = netrc.netrc().authenticators("api.wandb.ai")
        if not auth:
            raise ValueError("Authenticate Forge first")
        os.environ["WANDB_API_KEY"] = auth[2]
    api = wandb.Api(timeout=60)
    project = api._service_api.execute_graphql('query($e:String!,$p:String!){project(name:$p,entityName:$e){access}}', {"e": value["entity"], "p": value["project"]})["project"]
    if not project or project["access"].upper() != "PRIVATE":
        raise ValueError("Dashboard destination must be the existing private project")
    if value["final"]:
        committed = Path(api.artifact(value["source"]["artifact"]).get_entry("comparison.json").download(root=str(destination / "readback")))
        if sha(committed) != value["source"]["comparison_sha256"]:
            raise ValueError("Local comparison differs from its immutable published artifact")
    write(destination / "snapshot.json", value)
    progress = {"snapshot_id": value["snapshot_id"], "run_ids": [], "status": "publishing"}
    write(destination / "publishing.json", progress)
    config_filter = [expr.Config("dashboard_snapshot") == value["snapshot_id"]]
    for index, row in enumerate(value["attempts"]):
        run_id = f"dashboard-{value['snapshot_id']}-{index:02}"
        metrics = measurements(row, value["tool_usage"].get(row["attempt_id"], {}))
        # These are explicitly derived dashboard projections, never new agent attempts.
        with wandb.init(entity=value["entity"], project=value["project"], id=run_id,
                        name=f"{row['fixture']} · {row['arm']} · {row['repetition']}",
                        group=value["experiment_id"], job_type="dashboard-projection",
                        config={**row["identity"], "dashboard_snapshot": value["snapshot_id"],
                            "score_basis": value["score_basis"], "projection": True},
                        dir=str(destination), settings=wandb.Settings(disable_git=True, disable_code=True, console="off")) as run:
            if index == 0:
                artifact = wandb.Artifact("dashboard-" + value["snapshot_id"], type="recovery-dashboard")
                artifact.add_file(str(destination / "snapshot.json"), name="snapshot.json")
                artifact.add_file(__file__, name="publish_dashboard.py")
                logged = run.log_artifact(artifact).wait()
                progress["artifact"] = f"{value['entity']}/{value['project']}/{logged.name}"
        # Commit derived summaries through the Public API, then independently
        # read them back. Summary-only SDK runs lost metrics in real publication.
        api.run(f"{value['entity']}/{value['project']}/{run_id}").summary.update(metrics)
        progress["run_ids"].append(run_id)
        write(destination / "publishing.json", progress)
    count = len(value["attempts"])
    headline = f"{'Final' if value['final'] else 'Provisional'} comparison: {count} / 24 recorded attempts"
    intro = (f"## {headline}\n\n{value['score_basis']}. "
        "Six fixture families × two arms × two repetitions: 12 planned attempts per arm. Not-run attempts and unavailable checks are distinct from failures. "
        "Original failures remain in the record; no agent is rerun to populate this dashboard.\n\n"
        "Task tokens include schemas, repeated context and retries. Missing usage stays unavailable. "
        "Cost is an uncached-rate estimate/reservation, not settled billing. Agent seconds include finalization. "
        "CPU and peak memory cover the local container process family; remote inference resources are unavailable.\n\n"
        "REA availability is the treatment; a successful agent with zero REA calls does not establish a REA benefit. "
        "This small source-withheld Piskel exercise cannot establish general superiority. "
        f"Snapshot `{value['snapshot_id']}`; immutable source `{progress['artifact']}`.")
    if not value["final"]:
        intro += "\n\n**Incomplete:** the shared local Docker VM is unavailable. Native notebook drafts exist; final results and fresh-runtime verification remain pending."
    planned_per_arm = max(Counter(spec["arm"] for spec in value["planned"]).values())
    panels = [
        # The native view clipped grouped counts at the individual 0/1 range. Keep the full planned denominator visible on the axis.
        wr.BarPlot(title=f"Recorded attempts / checks available / passed — {planned_per_arm} planned per arm", metrics=["recorded_attempt", "checks_available", "passed_all_checks"], groupby=wr.Config("arm"), groupby_aggfunc="sum", groupby_rangefunc="none", range_x=(0, planned_per_arm), title_x="Attempts", layout=wr.Layout(x=0,y=0,w=24,h=8)),
        wr.BarPlot(title="Total task tokens per recorded attempt", metrics=["task_tokens"], max_runs_to_show=24, max_bars_to_show=24, layout=wr.Layout(x=0,y=8,w=12,h=10)),
        wr.BarPlot(title="Agent elapsed seconds per recorded attempt", metrics=["agent_seconds"], max_runs_to_show=24, max_bars_to_show=24, layout=wr.Layout(x=12,y=8,w=12,h=10)),
        wr.BarPlot(title="Cost estimate / reservation (USD)", metrics=["cost_estimate_or_reservation_usd"], max_runs_to_show=24,max_bars_to_show=24,layout=wr.Layout(x=0,y=18,w=12,h=10)),
        wr.BarPlot(title="Actual returned REA calls, including errors", metrics=["rea_returned_calls"], max_runs_to_show=24,max_bars_to_show=24,layout=wr.Layout(x=12,y=18,w=12,h=10)),
        wr.RunComparer(diff_only="split", layout=wr.Layout(x=0,y=28,w=24,h=12)),
    ]
    runset = wr.Runset(entity=value["entity"], project=value["project"], name="Recorded scored attempts only", filters=config_filter,
        pinned_columns=["run:name"], visible_columns=["config:arm", "config:fixture", "config:repetition", "summary:task_status", "summary:passed_all_checks", "summary:agent_lens_url", "summary:source_artifact"])
    report = wr.Report(entity=value["entity"], project=value["project"], title=f"REA animation recovery — {count} of 24 recorded", width="fluid",
        blocks=[wr.MarkdownBlock(text=intro),wr.PanelGrid(runsets=[runset],panels=panels),
            wr.H2(text="Every planned attempt"),wr.MarkdownBlock(text=navigation(value)),
            wr.H2(text="Animation and evidence walkthrough"),wr.MarkdownBlock(text="[Recover the animation](https://forge.coreweave.com/notebooks/Tm90ZWJvb2s6MTUyNzM%3D) · [What did REA change?](https://forge.coreweave.com/notebooks/Tm90ZWJvb2s6MTUyNzQ%3D)\n\nNotebook controls load recorded data and do not launch inference. Final publication requires saved-source readback and a fresh-runtime execution.")])
    report.save()
    progress["report_api_url"] = report.url
    write(destination / "publishing.json", progress)
    workspace = ws.Workspace(entity=value["entity"], project=value["project"], name=f"REA recovery — {count} of 24 recorded",
        sections=[ws.Section(name="Read this comparison", panels=[wr.MarkdownPanel(markdown=intro,layout=wr.Layout(x=0,y=0,w=24,h=12))],is_open=True,layout_settings=ws.SectionLayoutSettings(columns=1,rows=1)),
                  ws.Section(name="Recorded outcomes and resource use",panels=panels,is_open=True,layout_settings=ws.SectionLayoutSettings(columns=2,rows=3))],
        runset_settings=ws.RunsetSettings(filters=config_filter))
    workspace.save()
    progress["workspace_api_url"] = workspace.url
    write(destination / "publishing.json", progress)
    return verify(destination, value, progress)


def verify(destination: Path, value: dict, progress: dict) -> dict:
    import wandb
    import wandb_workspaces.reports.v2 as wr
    import wandb_workspaces.workspaces as ws

    observed_report = wr.Report.from_url(progress["report_api_url"])
    observed_workspace = ws.Workspace.from_url(progress["workspace_api_url"])
    count = len(value["attempts"])
    if observed_report.title != f"REA animation recovery — {count} of 24 recorded" or len(observed_report.blocks) != 6 or len(observed_workspace.sections) != 2:
        raise ValueError("Saved dashboard structure differs from the requested view")
    api = wandb.Api(timeout=60)
    expected_run_ids = {f"dashboard-{value['snapshot_id']}-{index:02}" for index in range(count)}
    selected_run_ids = {run.id for run in api.runs(f"{value['entity']}/{value['project']}",
        filters={"config.dashboard_snapshot": value["snapshot_id"]})}
    if selected_run_ids != expected_run_ids:
        raise ValueError("Dashboard filter does not select exactly this snapshot's recorded attempts")
    for index, row in enumerate(value["attempts"]):
        run_id = f"dashboard-{value['snapshot_id']}-{index:02}"
        expected = measurements(row, value["tool_usage"].get(row["attempt_id"], {}))
        actual = dict(api.run(f"{value['entity']}/{value['project']}/{run_id}").summary)
        if any(actual.get(k) != v for k,v in expected.items()):
            raise ValueError(f"Dashboard summary readback differs for {run_id}")
    write(destination / "report-readback.json", observed_report._to_model().model_dump(mode="json", by_alias=True, exclude_none=True))
    write(destination / "workspace-readback.json", observed_workspace._to_model().model_dump(mode="json", by_alias=True, exclude_none=True))
    result = {**progress,"status":"saved_and_api_verified", "recorded":count, "planned":24,"final":value["final"],
        "report_url":forge_url(progress["report_api_url"],value["entity"],value["project"]),
        "workspace_url":forge_url(progress["workspace_api_url"],value["entity"],value["project"]),
        "browser_verification":"pending", "source_sha256":sha(destination / "snapshot.json")}
    write(destination / "publication.json",result)
    return result


def archive_verification(destination: Path) -> dict:
    """Version the saved native views and exact metric readback separately."""
    import wandb

    receipt = destination / "verification-publication.json"
    if receipt.exists():
        return read(receipt)
    value = read(destination / "snapshot.json")
    publication = read(destination / "publication.json")
    if publication["status"] != "saved_and_api_verified":
        raise ValueError("Verify native views before archiving their receipts")
    with wandb.init(entity=value["entity"], project=value["project"],
                    id=f"dashboard-{value['snapshot_id']}-verification", job_type="dashboard-verification",
                    config={"verification_of": value["snapshot_id"]}, dir=str(destination),
                    settings=wandb.Settings(disable_git=True, disable_code=True, console="off")) as run:
        artifact = wandb.Artifact(f"dashboard-{value['snapshot_id']}-verification", type="recovery-verification")
        for name in ("snapshot.json", "publication.json", "report-readback.json", "workspace-readback.json", "summary-repair.json"):
            if (destination / name).exists():
                artifact.add_file(str(destination / name), name=name)
        artifact.add_file(__file__, name="source/publish_dashboard.py")
        artifact.add_file(str(Path(__file__).with_name("dashboard-requirements.txt")), name="source/dashboard-requirements.txt")
        logged = run.log_artifact(artifact).wait()
        reference = f"{value['entity']}/{value['project']}/{logged.name}"
        artifact_digest = logged.digest
    downloaded = Path(wandb.Api().artifact(reference).get_entry("snapshot.json").download(root=str(destination / "artifact-readback")))
    if sha(downloaded) != sha(destination / "snapshot.json"):
        raise ValueError("Dashboard artifact readback differs from its recorded source")
    result = {"artifact": reference, "digest": artifact_digest, "snapshot_sha256": sha(downloaded), "exact_source_match": True}
    write(receipt, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,required=True)
    args = parser.parse_args()
    publication = publish(args.root.resolve())
    publication["verification"] = archive_verification(args.root.resolve() / "dashboards" / publication["snapshot_id"])
    print(json.dumps(publication,indent=2))

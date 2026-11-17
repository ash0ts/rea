# Two recorded-data notebooks

The completed showcase uses
`wandb/rea-showcase/recovery-aa7c373605fd-comparison:v0`: all 24 scheduled attempts,
5/12 baseline passes and 9/12 REA-available passes under the uniform corrected
browser check. One baseline judgment is unavailable. Original results remain
intact. These counts describe this small exercise and do not establish a general
REA advantage.

The private [recovery notebook](https://forge.coreweave.com/notebooks/Tm90ZWJvb2s6MTUyNzM%3D)
and [comparison notebook](https://forge.coreweave.com/notebooks/Tm90ZWJvb2s6MTUyNzQ%3D)
were saved and read back as native source artifacts, then verified in separate
fresh Forge runtimes. Verification receipts retain the source hashes, package
versions, runtime IDs, screenshots and unchanged inference ledger. The
[walkthrough](WALKTHROUGH.md) links the final native report and saved workspace.

`recover_animation.py` reconstructs the visible animation beside the original,
offers a frame scrubber, original-layer inspection and exact RGBA differences, and
links the selected attempt to Agent Lens and its run artifacts. Its default is the
first successful scored REA attempt in manifest order and the paired baseline.
If no REA attempt succeeds, it labels that fact instead of inventing a successful demo.

`compare_recovery.py` retains all 24 scored attempts in paired outcome/resource
tables, exposes each checker criterion, and links every failure and success.
Returned tool-call counts show whether a treatment agent actually invoked REA;
interrupted calls remain inspectable in Agent Lens. Unknown measurements are not zero. The six fixture families are the cases; two
repetitions do not turn them into twelve independent cases.

The shared source of every displayed score is the frozen comparison artifact.
Playback is synthesized from recorded PNGs, never by executing a submitted decoder
inside a credentialed notebook. Animated PNG playback preserves translucent layers and is a viewing aid, while correctness
comes from exact PNG comparisons and the isolated browser-clock checker.
Playback starts paused; the reader can enable animation or inspect static frames
with the slider.
Frames, animation and difference masks use explicit display widths to preserve
their integer-scaled pixel sizes; single-layer images do not stretch across the
full notebook width.

```sh
uv sync --extra forge --extra notebooks --extra test
uv run python notebooks/publish_comparison.py --root .local/experiment \
  --ledger .local/execution-ledger.json
uv run marimo check notebooks/recover_animation.py notebooks/compare_recovery.py
uv run marimo edit notebooks/recover_animation.py
```

Publication pins an immutable `:vN` artifact reference in both sources. A notebook
with `UNPUBLISHED` stops with an explicit notice and is not a published result.
Do not use mutable aliases such as `latest` for a showcase.

Create native notebooks through Forge's supported create workflow, edit the runtime
from these checked-in sources, explicitly save, terminate the edit runtime, and
read back `currentVersion`. Download that committed source artifact and compare it
with the source. Then launch a fresh runtime and verify every reactive cell. A
standalone `.py` attachment is not equivalent to a saved Forge notebook.

Dependencies are pinned in PEP 723 metadata. Opening a notebook or changing a
selection only downloads recorded artifacts; it makes no inference requests.
Record hosted runtime launches and termination receipts against the separate
notebook allocation. Runtime reservations are estimates, not settled billing.

Visual contract: the recovery view answers whether a reusable decoder reconstructs
the recorded pixels and playback; the comparison view answers what differed in
these paired attempts. Tables provide exact accessible values. The source,
conditions, failures and evidence links stay adjacent to those values. No claim
extends beyond this small, source-withheld Piskel exercise.

The API key can create notebook records and read their committed artifacts, but
runtime launch requires an authenticated browser session. In the native editor,
open **Command palette → Show integrated terminal**, import the exact source from
its staging artifact into `/workspace/notebook.py` using `/opt/venv/bin/python`,
then restart the kernel to load its cells and explicitly **Save**. Do not paste
credentials into cells or terminal commands. Forge injects runtime authentication.
The staging artifact is not the publication: verify the native committed version:

```sh
uv run python notebooks/forge_notebooks.py --notebook-id NOTEBOOK_ID \
  --source notebooks/recover_animation.py --output .local/notebook-readback
```

If the editor normalizes source, inspect the downloaded file and reconcile the
checked-in source before the final readback. Pin the comparison only after all
24 scored records and uploads are present. Pass `--prior-root` for each retained
qualification campaign so setup failures remain visible in the published record.

The recovery notebook links each recorded tool-call ID directly to its Agent Lens
span and lists canonical Evidence IDs, provider, confidence, authority and
limitations. Its artifact link opens the immutable version containing the complete
`evidence/bundle.json`; the displayed summary does not replace that bundle. Pink
pixel differences mark any changed RGBA channel, including alpha-only changes.

A fresh hosted runtime was observed using marimo 0.25.1, W&B 0.31.0 and Pillow
13.0.0, even when an earlier draft requested marimo 0.25.2. The sources now pin the
observed compatible versions and check them before executing notebook cells.
Verify actual package versions in the fresh runtime; source metadata alone does
not establish that a host restored them. Local notebook checks use the same pins.

[The walkthrough](WALKTHROUGH.md) follows the first independently correct treatment
submission and its paired baseline, and states whether that agent actually used REA.

The comparison artifact owns the final publication receipts and immutable attempt
versions. Each attempt artifact contains a snapshot taken before its own upload
completed, so that snapshot can still say `upload_status: pending`. The final
comparison joins the completed upload receipt without rewriting that historical
snapshot. Recorded artifact-download hash checks are included in the comparison.
The comparison also retains the native run-summary repair for the VM-interrupted
baseline: the old uploader displayed a missing judgment as false. Its before/after
receipt records the correction to unavailable and verifies that the original
attempt file is unchanged. The current uploader preserves this distinction.

After all 24 attempts finish, run `verify_trace_joins.py --root .local/experiment`
before publishing the comparison. It matches each returned tool event to its
stored Agent Lens span and message response, including tool-call ID, parent turn,
trace identity, tool name, arguments and delivered response content. JSON payloads
are compared after parsing the SDK's serialized representation. Interrupted or
unanswered calls remain explicit.
The comparison retains this receipt; matching identifiers does not validate the
tool's substantive answer or replace the independent animation checks.
The complete saved provider messages remain in each attempt artifact. The frozen
Conversation SDK message projection displays ordinary text and tool calls; returned
provider reasoning fields are preserved in `messages.json`, not that projection.


## Uniform correction of recorded playback checks

The first campaign's browser clock advanced between driver calls. Correcting that
checker requires one uniform pass over all eligible retained previews, including
original successes and failures. Finish all 24 attempts and reconcile their owned
cleanup receipts first, then run:

```sh
uv run python notebooks/recheck_preview.py --root .local/experiment --publish
uv run python notebooks/publish_comparison.py --root .local/experiment \
  --ledger .local/execution-ledger.json
```

The recheck uses the frozen checker image, the corrected checked-in checker source
and fresh isolated containers. It never runs a model or submitted decoder. Only
previews whose original decoder and pixel checks passed are eligible; all other
original criteria remain unchanged. It refuses partial campaigns, changed source,
changed original records, and incomplete recheck directories. Original result
files remain byte-identical. A separate immutable verification artifact retains
per-case observations, original output hashes, correction source and cleanup IDs.

The comparison publisher refuses to publish a changed checker without this complete
published correction. Both original and corrected records appear in the comparison
notebook. Task statuses, inference usage and original performance measurements stay
unchanged; recheck resource measurements are separate. A request-limited attempt
can have a correct decoder, so paired tables show both task status and check pass.

## Native Forge dashboard and report

`publish_dashboard.py` publishes a saved workspace and a native report using
`wandb-workspaces==0.4.13`. It reads existing results only. Dashboard projection
runs use a separate job type and snapshot identity; they are never additional
agent attempts. The report links every planned attempt and its original Agent
Lens conversation and immutable artifacts. Unknown checks and resource values
remain unavailable rather than zero.

```sh
uv venv .local/dashboard-venv
uv pip install --python .local/dashboard-venv/bin/python \
  -r notebooks/dashboard-requirements.txt
.local/dashboard-venv/bin/python notebooks/publish_dashboard.py \
  --root .local/experiment
```

Before final comparison publication, views are explicitly provisional and show
how many of the 24 attempts have records. After `publish_comparison.py`, the same
command creates a separate final snapshot from its immutable comparison artifact;
it does not overwrite the provisional record. The publisher verifies that the
project is private, reads back both saved views, verifies the snapshot filter
selects exactly its recorded attempts, and compares every metric against source.
Browser verification remains a separate acceptance step.

The count plot uses the planned attempts per arm as its explicit axis maximum.
Native rendering otherwise clipped grouped counts at the individual 0/1 range,
even though API readback contained the correct sums. Inspect plotted marks as well
as stored metrics. The workspace uses one column for the introduction and two for
metric panels; retain before/after view definitions when repairing a saved display.

The real initial publication exposed empty server summaries after summary-only
SDK runs. The publisher now commits derived summaries through the Public API and
verifies them using a fresh client. The original campaign runs are not modified.
If publication is interrupted, its `publishing.json` retains created run/view IDs;
inspect and reconcile those resources before retrying. Saved source snapshots and
readback receipts remain under `dashboards/<snapshot-id>/` for artifact publication.

## Figures for the interim evidence review

`build_review_media.py` reproduces the twelve figures for the retained four-attempt
snapshot, including every planned slot, all nine unseen RGBA comparisons, the clock
diagnostic, resources and actual REA calls. It reads recorded files and never runs
submitted programs or inference. This is a generator for this specific interim
snapshot, not a final 24-attempt analysis. Its assertions reject different coverage.

```sh
uv venv .local/review-media-venv
uv pip install --python .local/review-media-venv/bin/python \
  -r notebooks/review-media-requirements.txt
.local/review-media-venv/bin/python notebooks/build_review_media.py \
  --root .local --output .local/review-media
```

The `raw/` directory extracted from the private evidence archive can replace
`.local` as the input root. Outputs include PNGs, editable SVGs, CSV/JSON tables,
claim boundaries and input SHA-256 hashes. The animated PNG is an inspection aid;
the static nine-frame audit is its reduced-motion alternative. Screenshots are
captured separately from the native product and retain their originals and crops.

For a complete comparison, `build_final_review_media.py` reads the immutable
`comparison.json` after the uniform preview correction. It requires all 24 uploaded,
cleaned-up records and reuses the dashboard's metric projection. It emits final
outcomes, original-versus-corrected judgments, per-family criteria, paired resources
and actual REA use, with CSV values and source hashes:

```sh
.local/review-media-venv/bin/python notebooks/build_final_review_media.py \
  --comparison .local/experiment/comparison/comparison.json \
  --output .local/final-review-media
```

The recovery notebook labels partial images left by a decoder that exited with an
error. The comparison explains that ordered exact matching can fail from wrong
pixels as well as wrong sequence. Neither display changes an agent result.

`build_partial_output_figure.py --root .local --output .local/final-review-media`
reproduces the retained translucent-layer failure example: original pixels,
partial output and an exact RGBA difference mask. Its assertions bind the figure
to the recorded attempt and frame; it never executes the failed decoder.

`build_output_gallery.py --root .local --comparison PATH --output PATH` shows one
retained unseen frame from every scored attempt beside its original. It labels
the complete corrected checker outcome separately, warns about partial output,
and leaves missing images visibly missing. A representative frame is an
illustration, not a replacement for the full pixel and playback checks. Its
JSON receipt retains each image path and hash.

## Standalone format-recovery comparison

The separate [format-recovery study](../format_recovery/README.md) compares the
same coding agent with ordinary tools, with REA, and with samples but no shipped
reader. Its 36 scored attempts and separate post-hoc coverage audit do not change
the original animation or dependency-review results. The study guide documents
the frozen controls, Python-only checker and reproduction commands.

`publish_format_recovery.py` requires all original attempts, the completed
added-input audit, and the separately frozen Unicode-ordering probe. Before writing the native Report, it reconciles actual model
contexts and responses, tool calls, prompt/settings/tool-schema equality, exact
staged-input inventories, Evidence exports, and every recorded primary and added
judgment. Report filters must select exactly the 36 scored IDs. Publication reads
saved results; it never runs an agent or submitted decoder.

`build_format_media.py` produces all-attempt outcomes and paired resource figures.
`build_format_example.py` shows the earliest primary-passing REA submission and its
paired baseline on a retained unseen file. A successful reconstruction is not an
attribution of that success to REA; the qualitative trace audit remains separate.

After inspecting the native Report, save its screenshot as
`media/native-format-report.png` and its verification receipt as
`ui-verification.json` under the experiment root. `publish_format_media.py` then
publishes the final media, saved Report definition and verification receipts in a
separate immutable artifact. Both publishers download and hash-check their files.
An interrupted publication keeps its progress receipt for reconciliation rather
than silently creating another resource.

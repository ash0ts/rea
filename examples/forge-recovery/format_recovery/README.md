# Recover a standalone decoder from a shipped reader

This controlled study compares an ordinary coding agent with the same agent using
REA, and includes a separate sample-only diagnostic. Four original laboratory
applications interpret compressed chunks, transactions, columns, and hierarchical
records. The deliverable is an executable Python decoder, graded on unseen inputs.
See [the research contract](RESEARCH.md) for the frozen design and claim limits.

The original Piskel and dependency-review campaigns remain separate. These are
newly authored, small applications, not measurements on commercial programs or
native binaries. Three repetitions measure consistency on four task families;
they do not create 36 independent targets.

## Prepare and qualify

Use the parent example's locked Python environment. Build artifacts and records
belong under `.local/`, never in Git. Controller credentials stay on the host.
Images are retained by owned idle containers so shared-daemon cleanup cannot
remove them during the campaign. Keep their receipts until cleanup is confirmed.

From the repository root, in a fresh checkout/output directory:

```bash
mkdir -p examples/forge-recovery/.local/format-recovery-build
git archive --format=tar \
  -o examples/forge-recovery/.local/format-recovery-build/rea-source.tar \
  c92cbcaf281bea28e16146c3555d58a2d62edf03
examples/forge-recovery/.venv/bin/python examples/forge-recovery/format_recovery/build_images.py
examples/forge-recovery/.venv/bin/python examples/forge-recovery/format_recovery/prepare.py \
  examples/forge-recovery/.local/format-prepared-v1
```

Preparation checks the independent Python expectations against the minified
JavaScript readers in isolated containers: 105 cases including qualification.
Original source, reference expectations and hidden inputs stay outside the agent
mounts. No source maps are generated. The final checker image has Python only,
so a submitted program cannot delegate decoding back to Node or the application.

The following commands start paid inference in the authorized private
`wandb/rea-showcase` project. They freeze configuration and retain every attempt.

```bash
examples/forge-recovery/.venv/bin/python examples/forge-recovery/format_recovery/run.py qualify \
  examples/forge-recovery/.local/format-recovery-v1 \
  --prepared examples/forge-recovery/.local/format-prepared-v1
examples/forge-recovery/.venv/bin/python examples/forge-recovery/format_recovery/run.py scored \
  examples/forge-recovery/.local/format-recovery-v1 \
  --prepared examples/forge-recovery/.local/format-prepared-v1
```

No uncertain request is retried. A completed scored attempt is reused only as its
existing record; interrupted attempts need explicit reconciliation. Do not change
the frozen source and reuse the same experiment directory. Qualification verifies
infrastructure and checking, independently of whether the model succeeds.

## Checks and publication

From `examples/forge-recovery`:

```bash
.venv/bin/python -m pytest format_recovery/test_study.py \
  tests/test_attempt_lifecycle.py tests/test_telemetry.py tests/test_sandbox.py tests/test_runner.py -q
FORMAT_PREPARED="$PWD/.local/format-prepared-v1" \
  .venv/bin/python -m pytest format_recovery/test_study.py -q
```

The explicit runtime check runs a known-correct decoder and an always-reject
control in the Python-only checker. Invalid-input credit requires successful
visible controls. Shared controller regressions cover budgets, cancellation,
cleanup and export failures; they do not establish coverage for arbitrary future
provider or lifecycle changes.

`notebooks/publish_format_recovery.py` derives the paired comparison, reconciles
stored Agent Lens spans, publishes a versioned evidence artifact and native Forge
Report, downloads the artifact to compare hashes, and reads back the saved Report.
It never starts inference or regrades a submission. It requires the frozen source
snapshot under the experiment's `frozen-source/` directory.

`notebooks/build_format_media.py` renders recorded results with matplotlib and
exports a table and media manifest. It also does not execute agents or submissions.

Before using a result as evidence, inspect its per-input judgment and actual
analysis trace. Returned Evidence and a focused query demonstrate that the workflow
ran; they do not establish that REA caused a correct implementation.

## Additional generalization coverage

The frozen primary generator left some relationships correlated. The separate
[`format_stress` audit](../format_stress/README.md) tests every saved decoder on
16 additional valid inputs and four format-specific invalid inputs per family.
It was designed after primary scoring began and is labeled post-hoc throughout.
It does not restart agents, repair their programs, or change primary scores.
Preparation validates 80 reference executions before inspecting any extra decoder
results. The artifact records both the frozen primary study and this later audit.
The same audit guide documents a further targeted Unicode-ordering probe across
all nine saved tree attempts. Four original-reader checks establish its expected
orders before grading; it also remains separate from both earlier suites.

## Pinned publication environment

After scoring and the separate audit finish, the publication extra supplies the
versions used for native panels and static figures. It is separate from REA's
runtime dependencies. These commands operate on saved records and make no
inference requests:

```bash
# From examples/forge-recovery; do not change a running campaign's environment.
uv sync --locked --extra forge --extra publication --extra test
.venv/bin/python notebooks/publish_format_recovery.py .local/format-recovery-v1 --derive-only
MPLCONFIGDIR=/tmp/rea-format-mpl .venv/bin/python notebooks/build_format_media.py \
  .local/format-recovery-v1 .local/format-recovery-v1/media
MPLCONFIGDIR=/tmp/rea-format-mpl .venv/bin/python notebooks/build_format_example.py \
  .local/format-recovery-v1 .local/format-recovery-v1/media
.venv/bin/python notebooks/publish_format_recovery.py .local/format-recovery-v1
```

Publication requires completed `stress-audit.json` and `ordering-probe.json`
receipts in the primary root, pointing to their directories and configuration
hashes. It verifies every
model context/response, known token count, prompt, tool schema and staged-input
inventory against stored Agent Lens and local records. Unknown usage remains
unknown. Native run display names identify format, arm and repetition; immutable
attempt IDs and submission hashes remain unchanged. Inspect both the saved
Report and downloaded artifact before treating publication as complete.

## Recorded comparison

Experiment `format-fdc129ce9840` retained all 36 scored attempts and three separate
qualification records. Both the ordinary-tools baseline and REA-available arm
passed every primary check in 12/12 attempts; the sample-only diagnostic passed
0/12. Both main arms also passed the separate broader post-hoc audit in 12/12.
A targeted Unicode-ordering probe passed 0/3 baseline and 1/3 REA tree attempts.
It was designed after source inspection and is not a primary or causal result.

REA consumed 1.59 times the aggregate task tokens and was slower in eight of
twelve pairs. Eleven treatments invoked REA; the remaining assigned treatment
is retained. Only seven attempts in each main arm saved an explanation. A passing
program does not imply a completed agent turn or full semantic equivalence.
These small original programs fit in model context; no large-program, native-binary,
or human-productivity conclusion is supported.

[Native comparison report](https://forge.coreweave.com/wandb/wandb/rea-showcase/reports/Standalone-format-recovery-—-ordinary-tools,-REA,-and-sample-only-control--VmlldzoxODI3ODcyMQ==) · [Immutable evidence](https://forge.coreweave.com/wandb/wandb/rea-showcase/artifacts/format-recovery-evidence/format-fdc129ce9840-evidence/v0/files).

The evidence artifact contains the exact executed source, all inputs, original
readers, submitted programs, canonical Evidence, model/tool records, judgments,
preparation history and post-run maintenance checks. Its 1,698 payload files and
manifest were downloaded and hash verified. Native UI inspection caught an
automatic aggregate-axis clipping issue; the report now sets that range explicitly.

The maintained controller shares finalization across the original and companion
runners, preserves cancellation through Evidence export and final cleanup, and
normalizes host memory units. These fixes were applied after scoring; they did not
change the frozen runtime or repair any submitted program. Reproduction with the
maintained code must use a fresh experiment directory and configuration identity.

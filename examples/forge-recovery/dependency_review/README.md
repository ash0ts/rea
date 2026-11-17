# Contained dependency-update review

This companion experiment asks what a candidate release does under three explicit
entry conditions: invoke its declared postinstall script, import its default entry,
or import with `PALETTE_DIAGNOSTICS=1`. It uses original laboratory packages, a dummy
token and a local recorder. It does not install registry packages or execute real
malware. Direct hook invocation does not test npm's installation policy.

Both agents get identical read-only list/read/search tools. The treatment additionally
gets pinned REA JavaScript analysis, version comparison and retained-Evidence tools
through a persistent MCP session. No target execution tool is exposed to either agent.
The prompt guides use of REA when available; this protocol differs from the animation
study's optional tool availability.

## Reproduce

Use the example's locked Python environment and Docker setup described in the parent
README. The controller needs Forge inference and telemetry credentials; containers
receive neither. Nothing here adds dependencies to REA's runtime.

```bash
# From examples/forge-recovery; this starts paid inference after local preparation.
.venv/bin/python dependency_review/run.py .local/dependency-review-new --build

# No inference: tests, media generation and evidence publication.
.venv/bin/python -m pytest dependency_review/test_review.py -q
/path/to/visual-python notebooks/build_dependency_media.py \
  .local/dependency-review-new /path/to/article-project
uv run --no-project --with wandb==0.31.0 --with wandb-workspaces==0.4.13 \
  python notebooks/publish_dependency_review.py .local/dependency-review-new
```

The media generator uses matplotlib. It reads recorded results only. The publication
script writes to the authorized private `wandb/rea-showcase` project, exports an
immutable evidence artifact, verifies downloaded hashes, and creates a native Report.
It never invokes a model. Review its fixed destination before adapting this example.

Use a fresh output directory. Existing attempts are never overwritten or retried.
`--build` builds the two local images; without it, matching tags must already exist.
Images are retained by owned containers for the campaign, with cleanup in `ExitStack`.
The REA revision is pinned by the shared runner. The experiment manifest freezes
input, oracle, code and configuration hashes, image IDs, tool schemas and attempt order
before qualification. The model remains `moonshotai/Kimi-K2.7-Code`, temperature 0.2,
with at most 4,096 output tokens per request, 16 requests, 300 seconds and $5 per attempt.
Reservations precede requests; the campaign ceiling is $50. Missing usage retains its
reservation. There are two qualification attempts and eight scored attempts, with
alternating arm order and one attempt per arm per case.

## What was run

Experiment `dependency-d79011a5a707` completed on November 9, 2026:

| Scored measure | Baseline | REA-assisted |
| --- | ---: | ---: |
| Reviews passing all checks | 4/4 | 4/4 |
| Correct scenario facts | 36/36 | 36/36 |
| Median task tokens | 12,213 | 223,946.5 |
| Median elapsed agent seconds | 47.9 | 67.2 |

All four treatment reviews analyzed both versions and obtained a comparison. Five
failed REA calls remain in their traces and resource totals. The separate qualification
pair also completed. The ledger's conservative total estimate for all ten attempts is
$0.84956714; this is not settled billing. No accuracy or efficiency advantage for REA
was observed on these small, readable packages.

The checker compares nine Boolean facts to 30 independent local scenario executions
(five pairs including qualification, two versions, three scenarios), and validates
exact source quotations. It does not automatically prove that a quotation supports an
explanation. A separate recorded assistant review examined those explanations; it is
not an independent human audit. The unused-helper control shares identical collector
bytes with the active-hook case but has no entry path that calls it.

All ten conversations and nested model/tool spans were read back. Tool IDs, arguments,
delivered results and parentage were reconciled with local records. All canonical REA
Evidence exports completed. All owned experiment containers have removed receipts.
Local files survive upload failures; cleanup failures retain ownership for retry.

The evidence artifact is `wandb/rea-showcase/dependency-d79011a5a707-evidence:v0`,
digest `6b5b86b8cf465b5b9d2e3a5982c8f5e1`: 245 payload files plus a manifest, all
downloaded and byte/hash verified. The private project Report is titled
**Dependency review — contained release-pair experiment**. It exposes every scored
attempt. Generated packages, images, traces and results are artifacts, not Git files.

## Verification and limits

The three focused regressions exercise source-read containment, deterministic archives,
the unused-helper control, and rejection of incorrect facts or fabricated quotations.
They passed for this revision. The runner reuses the example's sandbox, budget,
telemetry and cleanup primitives; these three tests do not establish new cancellation
or exporter-failure coverage. See the parent test suite for those shared contracts.

A live baseline container inspection confirmed no network, a read-only root, dropped
capabilities, no-new-privileges, only task input/work mounts and no model credential
variables. The controller executes only our fixture code to obtain reference behavior.
The agent cannot see the oracle. No result certifies arbitrary packages as safe: the
measured scope is three defined scenarios, with no explicit calls to exported helpers.

The first build-only attempt is retained separately. `git archive` initially ran from
the example subdirectory and produced an empty source archive. Resolving the checkout
root fixed that boundary before any model request. The scored campaign is separate
from the frozen animation experiment; its scores and artifacts were not changed.

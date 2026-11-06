# Run the controlled comparison

The controller owns credentials, inference, telemetry, scoring and artifact upload.
Both actors have the same Python/Node image and ordinary `execute` tool. Treatment
adds pinned REA and five unmodified MCP tool schemas from the running server. REA
itself remains local-only. The controller exports canonical Evidence before closing
the persistent MCP session; oversized tool responses link to the complete local JSON.

```sh
uv sync --extra test --extra forge
uv run pytest
REA_RECOVERY_PYTHON=.venv/bin/python sh scripts/build-containers.sh -- \
  .venv/bin/python -m forge_recovery.cli qualify --run-scored \
  --root .local/experiment --prepared .local/prepared --entity YOUR_ENTITY \
  --ledger .local/execution-ledger.json
uv run forge-recovery summarize --root .local/experiment
```

Resolve the destination from the authenticated account's memberships. A username
need not be an entity. This showcase uses `wandb/rea-showcase`, explicitly selected
by its owner after the account exposed no personal entity. The controller creates
the project as PRIVATE or refuses an existing non-private project.

The immutable experiment manifest freezes input hashes, original-app oracle hashes,
image IDs, code digests, prompt, model parameters, tool schemas and attempt order.
Run qualification first. It checks tool calling, Conversation SDK/Lens readback and
upload; it does not require successful recovery. Never replace a failed scored
attempt with a retry. An existing result is returned unchanged on resume. An
interrupted attempt retains its directory and resource receipt for inspection.

The pinned model is `moonshotai/Kimi-K2.7-Code`, temperature 0.2, output limit 16,384 tokens,
with SDK retries disabled. The published rates checked November 6, 2026 are $0.71/M
input and $3.50/M output; cached input is conservatively charged at the uncached
rate. Each call reserves the entire 262144-token context plus maximum output before
dispatch. Missing usage retains that reservation. A durable, locked ledger enforces
40 requests and $5 per attempt, $130 across attempts, and reserves $20 of the $150
ceiling for notebook verification. Share the ledger across every campaign directory.
Do not delete it to retry. Prices must be requalified for a later reproduction.

[Model catalog](https://docs.coreweave.com/products/inference/serverless/models) ·
[Published prices](https://coreweave.com/forge-pricing/inference-agents) ·
[Conversation SDK](https://github.com/wandb/weave#custom-agents)

One Conversation SDK conversation contains one root agent turn and nested model/tool
spans. The exact tool-call IDs connect replies to calls. The local messages include
every model context; provider usage therefore counts repeated schemas, context and
failed calls with known usage. Agent Lens readback is saved beside the result. Every
attempt has a W&B run and immutable result artifact; failed upload does not discard
local data or change the task outcome. The run link is attached to the root span.

Execution has 15 minutes, with the final 90 seconds reserved for independent checks.
Every checker command also has a bounded deadline. Cleanup and artifact upload may
continue after execution stops; their completion never permits further agent work.
The agent container's cgroup records the process family's CPU and peak memory,
including REA workers. Controller CPU and process-lifetime peak memory are separate.
Remote inference CPU/memory and billing settlement remain unavailable. Checker
resources are recorded separately. There is no cache shared between attempts.

The actor receives one visible project and the selected minified bundle. Each check
container receives only the standalone `decode.py` and one input; no pre-generated
frames, oracle, source maps or reference source. Checks cover visible and held-out
pixels, order, dimensions, FPS, hidden frames, sprite-sheet export, browser playback
and malformed/missing-chunk errors. Nonregular submission files are rejected before
upload. Container removal checks the retained full ID and owner label. Any failed
or unresolved cleanup retains its receipt and stops further attempts.

Qualification exposed a truncated tool call at the 8,192 output-token limit.
The runner preserves the exact partial response and its usage, then stops that
attempt as `budget_stop` before executing or replaying the incomplete call. It
never increases output limits or retries the paid request. Earlier qualification
records retain their original HTTP 400 outcome; a corrected runner uses a new
frozen experiment. Invalid-input regression passes also require that the decoder
ran successfully on both valid inputs, so a missing or broken decoder cannot
receive credit merely for exiting nonzero.

The final qualification and scored campaign use the increased 16,384-token
output allowance for both arms. Kimi-K2.7-Code, temperature, prompts, 40 requests,
15 minutes and $5 per-attempt limits remain fixed. The request reservation derives
from that same output limit. The user authorized further qualification and removed
the total spending restriction; the implementation retains its conservative $150
default because current execution is well below it. Every earlier experiment keeps
its original configuration and results.

The SDK's `APITimeoutError` is categorized as `timeout`, including when wrapped by
MCP finalization, rather than an infrastructure failure. Model requests may use
the remaining agent deadline instead of a separate three-minute cap; the total
attempt limit is unchanged. A timed-out request is never retried, and its uncertain
usage keeps the full reservation. Earlier records retain the original category.

Qualification also exposed premature controller admission: a 220,000-byte guard
stopped REA after eight requests despite the preceding response reporting 57,431
prompt tokens. Before scoring, both arms use a manifest-recorded 1 MiB serialized
request bound. This limits controller payload size, not model tokens; Forge owns
token-context admission. No history is silently truncated. The ledger still
reserves the full published model context plus the configured output allowance.

For one continuous campaign, use `qualify --run-scored` with the same arguments as
`qualify`. One controller lock and one image-retention scope cover qualification
and all scored attempts. The qualification gate is saved and checked before any
scored request; failure still closes every owned retention container. This avoids
an unreferenced-image gap between separate command invocations on a shared daemon.

The command above retains images continuously from their build through the
complete campaign. Standalone `qualify` and `run` commands are also available,
but the operator must preserve the frozen images between invocations.

Each newly built image is immediately referenced by an owned isolated container,
including while later images build. The same owner retains those references until
the optional command ends. Cleanup receipts live under `.local/build-retention/`;
failed cleanup keeps its identifiers. Only the owned temporary source archive is
removed; the script never prunes the shared Docker daemon.

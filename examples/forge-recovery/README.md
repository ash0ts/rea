# Recover an animation with REA

This external experiment asks an agent to recover a Piskel animation from a
minified application bundle and a saved project. The agent must deliver a reusable
decoder, exact composited frames, playback metadata, a preview and a sprite-sheet
export. Piskel's original renderer supplies the independent expected results.

The example does not change REA's CLI, MCP contracts, providers or dependencies.
It uses original generated artwork and an Apache-2.0 Piskel build. This is a
source-withheld exercise on an existing public format, not a claim to discover a
new format. A model may have encountered Piskel during training.

## Prepare

Use Docker, Git, uv, and Python 3.11 or later. The container provides REA's pinned
Node toolchain without upgrading the host's Node installation.

```sh
cd examples/forge-recovery
uv sync --extra test
uv run playwright install chromium
uv run forge-recovery prepare --root .local/prepared
uv run pytest tests/test_benchmark.py tests/test_sandbox.py
```

Preparation builds pinned Piskel source, creates six fixture families and a separate
qualification fixture, and freezes hashes. The agent receives only a minified
bundle and its visible project file. Source maps, unminified source, the original
renderer and held-out cases stay outside its container. Missing source maps are
an intentional limitation; the selected bundle's bytes are not rewritten.

Prepared directories are immutable. Reusing one verifies its input/oracle hashes;
an incomplete preparation must use a new directory. Build filenames include an
upstream timestamp, so the prepared artifact, not a later rebuild, is the byte-level
reproduction unit. Keep `.local/`, images and bundles out of Git.

## Submission contract

The agent writes `decode.py` at the root of its workspace. It accepts
`python decode.py INPUT.piskel OUTPUT_DIRECTORY` and creates:

- `manifest.json`: `width`, `height`, `fps`, `hidden_frames`, `playback_order`, and
  `frames` (ordered PNG basenames, including hidden frames).
- One composited RGBA PNG for every source frame, preserving original order.
- `spritesheet.png`, containing all frames in one horizontal row.
- `index.html`, a self-contained preview with play/pause, a frame scrubber and a
  sprite-sheet download. Start paused; render at native resolution in a canvas.
  Use a range input with accessible name `Frame`, a button named `Play`/`Pause`,
  and a download link named `Download sprite sheet`. Network dependencies are unavailable.

The decoder must accept unseen projects from the same fixture family. It must
exit nonzero for malformed JSON or missing image chunks. Its source and generated
files are retained even when checking fails. The checker validates exact decoded
pixels rather than screenshots or the agent's own assertion of correctness.

## Authority and cleanup

Candidate programs run only in newly owned, network-disabled containers. The host
controller retains the exact container ID and owner label in a cleanup receipt.
Container credentials are absent and the input mount is read-only. Cleanup errors
retain the receipt for retry; never sweep containers by name prefix or PID.

The reference browser is run by the benchmark builder on the trusted pinned
open-source application. Candidate code is never run directly by the host checker.

## Checker and transport regressions

The preview checker installs Playwright's clock before navigation and pauses it
before manual playback ticks. Driver/RPC time must not advance the browser clock
between samples. A retained 13-FPS preview exposed a false timing failure in the
original checker: 1,944 ms of requested ticks advanced its unpaused clock by
2,465 ms. The same output passed with the clock paused. Original campaign records
remain immutable; every eligible retained preview must receive the same corrected
check before reporting final playback outcomes.

With an already built checker image, run the real browser regressions explicitly:

```sh
REA_RECOVERY_CHECKER_IMAGE=rea-forge-recovery-checker:v1 \
  uv run pytest tests/test_preview_clock.py
```

They exercise 13-FPS animation-frame playback, hidden frames and a wrong-FPS
negative control under driver delay. They are skipped when no checker image is
selected. See [Playwright's manual clock guidance](https://playwright.dev/python/docs/clock#tick-through-time-manually-firing-all-the-timers-consistently).

Docker start, execution transport and cleanup calls have deadlines. A daemon
connection failure is an infrastructure error, distinct from a generated command
exiting or timing out. The container ID/owner receipt remains available when
cleanup or a late startup response cannot be verified.

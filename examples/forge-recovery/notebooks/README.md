# Two recorded-data notebooks

`recover_animation.py` reconstructs the visible animation beside the original,
offers a frame scrubber, original-layer inspection and exact RGBA differences, and
links the selected attempt to Agent Lens and its run artifacts. Its default is the
first successful scored REA attempt in manifest order and the paired baseline.
If no REA attempt succeeds, it labels that fact instead of inventing a successful demo.

`compare_recovery.py` retains all 24 scored attempts in paired outcome/resource
tables, exposes each checker criterion, and links every failure and success.
Unknown measurements are not zero. The six fixture families are the cases; two
repetitions do not turn them into twelve independent cases.

The shared source of every displayed score is the frozen comparison artifact.
Playback is synthesized from recorded PNGs, never by executing a submitted decoder
inside a credentialed notebook. GIF playback is a viewing aid, while correctness
comes from exact PNG comparisons and the isolated browser-clock checker.

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
Hosted verification is bounded by the experiment's separate $20 reservation.

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

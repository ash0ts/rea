# Research contract

Question: does adding REA's JavaScript analysis and retained Evidence tools help
one fixed agent recover Piskel animations under the same task budget?

Pins: REA `c92cbcaf281bea28e16146c3555d58a2d62edf03`; Piskel
`745caa20ebebbe3991247064ccc5b51ee9a5490d`. Preparation records exact bundle,
fixture, generator, image and browser identities. Agent input excludes source
maps and original source; the reference renderer is restricted to the evaluator.

Six fixture families are basic, opacity, non-square, multiple chunks, hidden
frames and legacy single-image storage. Each has a visible instance and an unseen
instance with different dimensions/timing/pixels where applicable. Qualification
uses a separate fixture. Two repetitions are repeated observations, not new tasks.

Freeze both arms before scored execution. The baseline has file/search/code tools;
the treatment adds REA. Both use the same model, prompt, ordinary tools, fixture
bytes, limits and checker. Alternate arm order. Each run gets a fresh workspace;
there is no cross-attempt agent memory or warm REA Evidence cache.

Task pass requires exact output pixels, ordering, dimensions, FPS, hidden-frame
playback, sprite-sheet export, held-out generalization, malformed-input rejection
and a working preview. Report each axis, all attempts and denominators. Tool errors,
budget exhaustion, model mistakes, infrastructure failure and export failure are
different outcomes. Preserve failed attempts; no best-of-N replacement.

Measure provider-reported input/output tokens across all requests, including tool
schemas and retries; wall time; CPU and peak memory of the local container process
family; controller resource measurements separately; and billable usage or its
explicit estimate. Missing measurements are unknown. Remote inference resources
and platform storage charges are not inferred from local measurements.

The first successful treatment attempt in manifest order supplies the walkthrough,
alongside its paired baseline. All results remain inspectable. Qualification is
excluded from the scored denominator. Changes after freezing create a new campaign.
No universal model ranking or statistically established general REA advantage is
claimed from this small sample.

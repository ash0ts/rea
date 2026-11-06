# Follow one recovered animation

Final native publication is pending the complete 24-attempt comparison. The pair
below is already recorded and independently checked. It is the first treatment
attempt in manifest order whose submitted decoder passes every check.

1. Open **Recover the animation** and keep the default `basic`, repetition `1`.
   Start with the unseen nine-frame input, then switch to the visible six-frame
   input. Scrub every frame and inspect the RGBA difference: the treatment output
   matches the pinned Piskel renderer exactly. The paired baseline has no decoder
   and displays an explicit unavailable-output notice.
2. Expand the independent checker details. Both inputs passed pixels, ordering,
   dimensions, FPS, hidden-frame metadata, sprite-sheet export and the isolated
   browser preview. The submitted decoder also rejected malformed JSON and a
   missing chunk. Fresh check containers received only the program and one input;
   they could not reuse its previously generated frames.
3. Open the [final decoder-writing tool span](https://forge.coreweave.com/wandb/wandb/rea-showcase/weave/agents/conversations/recovery-aa7c373605fd-basic-rea-1?chatTab=spans&convTurn=1&chatTrace=ad9dc5a45b1c75886820ab9728edc060&span=4f8d2628102604f4)
   in Agent Lens. Inspect its matching `functions.execute:36` call and result,
   then navigate backward to the model request and earlier investigation. The
   [paired baseline conversation](https://forge.coreweave.com/wandb/wandb/rea-showcase/weave/agents/conversations/recovery-aa7c373605fd-basic-baseline-1)
   shows its unsuccessful investigation through the same 40-request limit.
4. Open the immutable [treatment artifact](https://forge.coreweave.com/wandb/wandb/rea-showcase/artifacts/recovery-attempt/attempt-recovery-aa7c373605fd-basic-rea-1/v0)
   and [baseline artifact](https://forge.coreweave.com/wandb/wandb/rea-showcase/artifacts/recovery-attempt/attempt-recovery-aa7c373605fd-basic-baseline-1/v0).
   They preserve submissions, messages, events, checker outputs and Agent Lens
   readback. Artifact download and notebook controls do not launch inference.
5. Open **What did REA change?** to inspect every scored attempt, criterion and
   failure, rather than treating this one pair as the comparison's conclusion.

This successful treatment agent invoked **zero REA tools**. Its success therefore
cannot be attributed to REA analysis. The treatment makes REA available; it does
not force the model to use it. The notebook reports actual returned tool-call
counts, including errors. Attempts that do invoke REA retain canonical Evidence
and link individual analysis steps in the same way.

Both attempts reached the request limit and retain `budget_stop` as their task
status. Independent checker success is a separate fact: treatment passed, baseline
failed. The treatment used 2,065,166 reported task tokens and 519.86 agent seconds;
its uncached-rate estimate was $1.5539. The paired baseline used $0.2260 and 81.75
agent seconds. These are observations of one pair, not an estimate of a general
REA effect. Remote inference resources and settled billing remain unavailable.

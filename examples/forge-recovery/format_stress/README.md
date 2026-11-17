# Additional coverage for saved decoders

This is a **post-hoc generalization audit**, separate from the frozen primary
format-recovery study. See [RESEARCH.md](RESEARCH.md) for timing, selection, and
claim limits. It makes no paid inference calls and never edits a submitted program.

From the repository root, with the original experiment and its retained images:

```bash
examples/forge-recovery/.venv/bin/python examples/forge-recovery/format_stress/run.py prepare \
  examples/forge-recovery/.local/format-recovery-v1 \
  examples/forge-recovery/.local/format-recovery-v1-stress-v4
# After all 36 original attempts have completed:
examples/forge-recovery/.venv/bin/python examples/forge-recovery/format_stress/run.py grade \
  examples/forge-recovery/.local/format-recovery-v1 \
  examples/forge-recovery/.local/format-recovery-v1-stress-v4
```

Use a fresh audit output directory for reproduction. Preparation freezes 80
reference executions (16 valid and four semantic invalid cases for each of four
formats) before inspecting any submitted decoder's added results. Every expectation
must match the original frozen JavaScript reader. Grading copies only the original
`decode.py` into the Python-only offline checker and preserves each input's output,
exit status and exact comparison. Two original visible controls gate rejection
credit. Missing submissions stay missing. Original primary scores stay unchanged.

The `-v4` directory records the executed preparation. The first local preparation
was denied access to the Docker socket by the host sandbox before any reference
execution; that failed preparation and its reconciled ownership receipt are
retained separately. It was not a model attempt or a scored decoder execution.

The second preparation passed the reader reference checks but failed a coverage
regression: active state was correlated with parent-group parity. The third
preparation fixes that relationship and passes both coverage regressions and all
80 reference checks. No submitted decoder was graded during preparation.

The fourth preparation uses identical inputs to the third and completes the
prepare/grade receipt handoff to publication. It passed all 80 reference checks
before grading. Preparation history is retained in the evidence artifact.

## Separate Unicode-ordering probe

Source inspection of the first tree decoders identified a further gap: Python
string comparison uses Unicode code points, while the original JavaScript
comparator uses UTF-16 code units. Emoji U+1F600 and halfwidth katakana U+FF76
distinguish those orders. `ordering_probe.py` freezes four small files across
versions and reverse flags and validates their expected output against the
original reader before grading any saved program.

This targeted probe was prepared after 29 primary attempts had completed. It is
post-hoc, covers every one of the nine tree attempts, and changes neither primary
nor broader stress scores. It makes no inference calls or submission repairs.
Missing programs remain missing. Expected answers are outside the decoder's
Python-only container; only the four binary inputs are mounted.

```bash
examples/forge-recovery/.venv/bin/python examples/forge-recovery/format_stress/ordering_probe.py prepare \
  examples/forge-recovery/.local/format-recovery-v1 \
  examples/forge-recovery/.local/format-recovery-ordering-v2
# After all 36 original attempts have completed:
examples/forge-recovery/.venv/bin/python examples/forge-recovery/format_stress/ordering_probe.py grade \
  examples/forge-recovery/.local/format-recovery-v1 \
  examples/forge-recovery/.local/format-recovery-ordering-v2
```

Use a new output directory for reproduction. The ungraded first preparation is
retained: its planned grader would have mounted the directory containing expected
answers. Input staging was corrected before any submitted program ran. The final
preparation has identical input hashes and four passing original-reader checks.

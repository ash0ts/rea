"""Explain the first successful REA reconstruction using saved checker outputs."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch


def build(root, output):
    config = json.loads((root / "experiment.json").read_text())
    selected = None
    for spec in config["attempts"]:
        result_file = root / "attempts" / spec["attempt_id"] / "result.json"
        if spec["arm"] != "rea" or not result_file.exists():
            continue
        result = json.loads(result_file.read_text())
        if result.get("checker", {}).get("behavior_pass"):
            selected = result
            break
    if selected is None:
        raise ValueError("No successful REA decoder is available; do not invent an example")
    case = next(c for c in selected["checker"]["cases"] if c["name"] == "heldout-09.bin")
    assert case["passed"] and case["actual"] == case["expected"]
    fixture, repetition = selected["fixture"], selected["repetition"]
    paired = next(s for s in config["attempts"] if s["fixture"] == fixture and s["repetition"] == repetition and s["arm"] == "baseline")
    baseline = json.loads((root / "attempts" / paired["attempt_id"] / "result.json").read_text())
    raw = (Path(config["prepared"]) / "oracle" / fixture / case["name"]).read_bytes()
    records = case["actual"]["records"]
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "figure.facecolor": "#fafaf7", "font.size": 12})
    fig, ax = plt.subplots(figsize=(12, 6.7))
    ax.set(xlim=(0, 12), ylim=(0, 6.7)); ax.axis("off")
    ax.text(.2, 6.25, f"Recover {len(records)} records without the original application", fontsize=21, weight="bold", color="#233342")
    ax.text(.2, 5.8, f"{fixture} · repetition {repetition} · unseen version {case['actual']['version']} file · recorded checker output", fontsize=11, color="#536471")
    for x, title in ((.2, "A new binary file"), (4.3, "The saved decoder"), (8.1, "Recovered records")):
        ax.text(x, 4.95, title, weight="bold", fontsize=15, color="#233342")
    hex_lines = [raw[i:i+8].hex(" ") for i in range(0, 40, 8)]
    ax.text(.2, 4.45, "\n".join(hex_lines), va="top", family="DejaVu Sans Mono", fontsize=11, linespacing=1.8)
    ax.text(.2, 2.6, f"{len(raw):,} bytes\nDifferent values and record count\nfrom either visible example", va="top", fontsize=11, linespacing=1.7, color="#536471")
    ax.text(4.3, 4.4, "decode.py", family="DejaVu Sans Mono", fontsize=19, color="#227963")
    ax.text(4.3, 3.8, "Python standard library\nFresh offline container\nApplication and Node absent\nOnly the submitted program copied", va="top", fontsize=11, linespacing=1.9, color="#536471")
    ax.text(8.1, 4.4, "ID       VALUE    ACTIVE", family="DejaVu Sans Mono", fontsize=11, weight="bold")
    shown = records[:4]
    ax.text(8.1, 3.95, "\n".join(f"{r['id']:<8} {r['value']:>6}    {str(r['active']).lower()}" for r in shown), family="DejaVu Sans Mono", fontsize=11, va="top", linespacing=1.9)
    ax.text(8.1, 2.25, f"First {len(shown)} of {len(records)} records shown.\nAll fields and ordering matched,\nincluding labels omitted here.", va="top", fontsize=10.5, linespacing=1.7, color="#536471")
    for a, b in ((3.35, 4.05), (7.2, 7.9)):
        ax.add_patch(FancyArrowPatch((a, 3.4), (b, 3.4), arrowstyle="-|>", mutation_scale=16, color="#788b95", linewidth=1.7))
    bc, tc = baseline.get("checker", {}), selected["checker"]
    ax.plot([.2, 11.8], [1.25, 1.25], color="#ccd5d7")
    ax.text(.2, .85, f"Same task: ordinary tools {bc.get('valid_passed', 'unavailable')}/12 unseen files · REA {tc['valid_passed']}/12", fontsize=13, weight="bold", color="#233342")
    ax.text(.2, .35, "This establishes a working standalone reconstruction. This pair does not establish an incremental REA benefit.", fontsize=10.5, color="#536471")
    fig.savefig(output / "format-reconstruction.png", dpi=180, bbox_inches="tight")
    fig.savefig(output / "format-reconstruction.svg", bbox_inches="tight")
    plt.close(fig)
    proof = {"attempt_id": selected["attempt_id"], "paired_baseline": paired["attempt_id"], "hidden_input": case["name"],
             "input_sha256": hashlib.sha256(raw).hexdigest(), "all_records": records,
             "scope": "Saved checker output from earliest successful REA attempt in frozen order; not a new execution or a causal tool claim."}
    (output / "format-reconstruction.json").write_text(json.dumps(proof, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path); parser.add_argument("output", type=Path)
    args = parser.parse_args(); build(args.root.resolve(), args.output.resolve())

"""Show one retained unseen frame per attempt, with its complete checker outcome."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/rea-review-matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

FAMILIES = ["basic", "opacity", "non_square", "chunks", "hidden", "legacy"]
NAMES = ["Basic", "Translucent layers", "Non-square", "Image chunks", "Hidden frames", "Legacy storage"]
CONDITIONS = [("baseline", 1), ("rea", 1), ("baseline", 2), ("rea", 2)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help=".local or extracted raw/ evidence directory")
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, out = args.root.resolve(), args.output.resolve()
    comparison = json.loads(args.comparison.read_text())
    rows = comparison["summary"]["attempts"]
    assert len(rows) == 24 and comparison["preview_recheck"]["complete"]
    by_key = {(r["fixture"], r["arm"], r["repetition"]): r for r in rows}
    assert set(by_key) == {(f, arm, rep) for f in FAMILIES for arm, rep in CONDITIONS}
    out.joinpath("figures").mkdir(parents=True, exist_ok=True)
    out.joinpath("data").mkdir(exist_ok=True)
    sources = {}

    def retain(path):
        sources[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
        return path

    def composite(path):
        image = Image.open(retain(path)).convert("RGBA")
        background = Image.new("RGBA", image.size)
        background.putdata([(225, 230, 232, 255) if (x // 3 + y // 3) % 2 else (250, 251, 249, 255)
                            for y in range(image.height) for x in range(image.width)])
        return Image.alpha_composite(background, image)

    plt.rcParams.update({"font.family": "DejaVu Sans", "svg.fonttype": "none", "svg.hashsalt": "rea-recovery-gallery"})
    fig, axes = plt.subplots(6, 5, figsize=(12, 14))
    fig.set_facecolor("#fafbf9")
    fig.subplots_adjust(left=.03, right=.99, top=.88, bottom=.08, wspace=.18, hspace=.55)
    inventory = []
    for y, (family, title) in enumerate(zip(FAMILIES, NAMES)):
        original = root / "prepared-v2/oracle" / family / "heldout"
        expected = json.loads(retain(original / "expected.json").read_text())
        frame_index = 3
        assert expected["frame_count"] > frame_index
        axes[y, 0].imshow(composite(original / f"frame-{frame_index:03}.png"), interpolation="nearest")
        axes[y, 0].set_title(f"{title}\n{expected['width']} × {expected['height']} · Piskel", fontsize=10, fontweight="bold")
        for x, (arm, rep) in enumerate(CONDITIONS, 1):
            row = by_key[family, arm, rep]
            folder = root / "experiment-v5/attempts" / row["attempt_id"] / "checks/heldout/verified-output"
            ax = axes[y, x]
            checked = (row.get("checker") or {}).get("passed")
            label = "Pass" if checked is True else "Fail" if checked is False else "No check"
            color = "#24786a" if checked is True else "#bd4f43" if checked is False else "#56616a"
            decoder = ((row.get("checker") or {}).get("cases") or {}).get("heldout", {}).get("decoder", {})
            partial = decoder.get("exit_code") not in (None, 0)
            item = {"attempt_id": row["attempt_id"], "input": "heldout", "frame_index": frame_index,
                    "overall_check": checked, "decoder_exit_code": decoder.get("exit_code"), "image": None}
            try:
                manifest = json.loads(retain(folder / "manifest.json").read_text())
                name = manifest["frames"][frame_index]
                if not isinstance(name, str) or Path(name).name != name:
                    raise ValueError("Invalid frame name")
                candidate = folder / name
                ax.imshow(composite(candidate), interpolation="nearest")
                item["image"] = str(candidate.relative_to(root))
                if partial:
                    ax.text(.5, -.08, "Partial output · decoder failed", transform=ax.transAxes,
                            ha="center", fontsize=9, color=color)
            except (OSError, KeyError, ValueError, IndexError) as error:
                ax.text(.5, .5, "No retained\nframe to display", transform=ax.transAxes,
                        ha="center", va="center", fontsize=10, color="#56616a")
                item["display_error"] = f"{type(error).__name__}: {error}"
            ax.set_title(f"{'Base' if arm == 'baseline' else 'REA'} · rep. {rep}\n{label}", fontsize=10, color=color)
            inventory.append(item)
        for ax in axes[y]:
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_facecolor("#f1f4f4")
            for spine in ax.spines.values():
                spine.set_visible(False)
    fig.suptitle("What did each submitted program leave behind?", fontsize=21, fontweight="bold", y=.97)
    fig.text(.03, .915, "Unseen input · fourth image in each saved manifest · original renderer in the first column\n"
             "The label is the complete attempt’s corrected check result, not a judgment from this picture.", fontsize=12)
    fig.text(.03, .025, "All 24 scheduled attempts are shown. Near-identical images can fail exact pixels, playback, or export.\n"
             "A missing frame is not an all-zero image. Complete PNG sets and independent checks remain in the artifacts.", fontsize=11)
    for extension in ("png", "svg"):
        fig.savefig(out / f"figures/all-retained-outputs.{extension}", dpi=160, bbox_inches="tight",
                    metadata={"Date": None} if extension == "svg" else None)
    plt.close(fig)
    receipt = {"comparison_sha256": hashlib.sha256(args.comparison.read_bytes()).hexdigest(),
               "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "frame_index": 3, "input": "heldout", "attempts": inventory, "source_sha256": sources,
               "limitation": "One recorded frame is an illustration; the complete checker outcome appears separately."}
    (out / "data/output-gallery.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"attempts": len(inventory), "displayed_outputs": sum(x["image"] is not None for x in inventory)}))


if __name__ == "__main__":
    main()

"""Render the complete, uniformly checked comparison without executing submissions."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault('MPLCONFIGDIR', '/tmp/rea-review-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from publish_dashboard import measurements

FAMILIES = ['basic', 'opacity', 'non_square', 'chunks', 'hidden', 'legacy']
NAMES = ['Basic', 'Translucent layers', 'Non-square', 'Image chunks', 'Hidden frames', 'Legacy storage']
CONDITIONS = [('baseline', 1), ('rea', 1), ('baseline', 2), ('rea', 2)]
PASS, FAIL, UNKNOWN = '#24786a', '#bd4f43', '#e2e7ec'
BASE, REA, INK = '#287ca4', '#c06c28', '#202c3b'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comparison', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.comparison.read_text())
    summary, original = data['summary'], data['original_summary']
    rows = summary['attempts']
    assert len(rows) == 24 and len({r['attempt_id'] for r in rows}) == 24
    assert {(r['fixture'], r['arm'], r['repetition']) for r in rows} == {
        (f, arm, rep) for f in FAMILIES for arm, rep in CONDITIONS}
    assert all(r.get('upload_status') == 'complete' and r.get('cleanup_status') == 'complete'
               and 'total_elapsed_seconds' in r for r in rows)
    assert data['preview_recheck']['complete'], 'Use the uniformly corrected final comparison'
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    charts = out / 'figures'
    charts.mkdir(exist_ok=True)
    tables = out / 'data'
    tables.mkdir(exist_ok=True)
    by_key = {(r['fixture'], r['arm'], r['repetition']): r for r in rows}
    original_by_key = {(r['fixture'], r['arm'], r['repetition']): r for r in original['attempts']}
    projected = {r['attempt_id']: measurements(r, data['tool_usage'].get(r['attempt_id']) or {}) for r in rows}
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11, 'text.color': INK,
                        'figure.facecolor': '#fafbf9', 'axes.facecolor': '#fafbf9',
                        'axes.spines.top': False, 'axes.spines.right': False,
                        'axes.spines.left': False, 'axes.spines.bottom': False,
                        'svg.fonttype': 'none', 'svg.hashsalt': 'rea-recovery-final'})
    manifest = []

    def save(fig, name, caption):
        fig.savefig(charts / f'{name}.png', dpi=160, bbox_inches='tight')
        fig.savefig(charts / f'{name}.svg', bbox_inches='tight', metadata={'Date': None})
        plt.close(fig)
        manifest.append({'file': name + '.png', 'caption': caption})

    def passed(row):
        value = (row.get('checker') or {}).get('passed')
        assert value is None or isinstance(value, bool)
        return value

    def outcome_grid(ax, source, compact=False):
        for y, family in enumerate(FAMILIES):
            for x, (arm, rep) in enumerate(CONDITIONS):
                value = passed(source[family, arm, rep])
                ax.add_patch(Rectangle((x-.45, y-.4), .9, .8,
                                      facecolor=PASS if value is True else FAIL if value is False else UNKNOWN))
                ax.text(x, y, 'Pass' if value is True else 'Fail' if value is False else 'No check',
                        ha='center', va='center', color='white' if value is not None else INK,
                        fontsize=9 if compact else 12)
        ax.set_xlim(-.5, 3.5)
        ax.set_ylim(5.5, -.5)
        ax.set_xticks(range(4), ['Base\nrep. 1', 'REA\nrep. 1', 'Base\nrep. 2', 'REA\nrep. 2'])
        ax.set_yticks(range(6), NAMES)
        ax.tick_params(length=0, pad=8)

    fig, ax = plt.subplots(figsize=(8, 6.2))
    fig.subplots_adjust(left=.25, right=.98, top=.83, bottom=.18)
    outcome_grid(ax, by_key)
    totals = {arm: {'passed': sum(passed(r) is True for r in rows if r['arm'] == arm),
                    'failed': sum(passed(r) is False for r in rows if r['arm'] == arm),
                    'unavailable': sum(passed(r) is None for r in rows if r['arm'] == arm)}
              for arm in ['baseline', 'rea']}
    fig.suptitle('Every scheduled attempt remains in the comparison', fontsize=18, fontweight='bold')
    fig.text(.03, .035, '24 recorded attempts · 12 per arm · six fixture families\nUniform corrected browser checks. No check is not a failed decoder.', fontsize=11)
    save(fig, 'final-outcomes', 'All scheduled attempts, including unavailable judgments. Repetitions belong to the same six families; this is not a population-level REA effect estimate.')

    fig, axes = plt.subplots(1, 2, figsize=(12, 5.7))
    fig.subplots_adjust(left=.15, right=.99, wspace=.57, top=.79, bottom=.18)
    for ax, source, title in zip(axes, [original_by_key, by_key], ['Original checks', 'Uniform corrected checks']):
        outcome_grid(ax, source, True)
        ax.set_title(title, loc='left', fontweight='bold', pad=18)
    changed = [r['attempt_id'] for r in rows if passed(r) != passed(original_by_key[r['fixture'], r['arm'], r['repetition']])]
    change_label = 'One overall judgment changed' if len(changed) == 1 else f'{len(changed)} overall judgments changed'
    fig.suptitle(f'{change_label} after the uniform preview check', fontsize=18, fontweight='bold')
    fig.text(.02, .025, 'Same submitted files. Original records retained. Model usage, pixels, task statuses and resource measurements are unchanged.', fontsize=10)
    save(fig, 'original-versus-corrected', 'Every eligible retained preview received the same corrected check. This changes measurement, not the agent investigation or submitted decoder.')

    criteria = [('pixels', 'Pixels'), ('frame_order', 'Order'), ('dimensions', 'Size'), ('fps', 'FPS'),
                ('hidden_frames', 'Hidden'), ('sprite_sheet', 'Sheet'),
                ('preview_playback', 'Play'), ('preview_scrubbing', 'Scrub'), ('preview_download', 'Export')]
    criteria_rows = []
    fig, axes = plt.subplots(3, 2, figsize=(13, 13))
    fig.subplots_adjust(left=.12, right=.99, top=.92, bottom=.12, wspace=.31, hspace=.42)
    for ax, family, title in zip(axes.flat, FAMILIES, NAMES):
        labels = []
        for condition_index, (arm, rep) in enumerate(CONDITIONS):
            row = by_key[family, arm, rep]
            metrics = projected[row['attempt_id']]
            for case_index, case in enumerate(['visible', 'heldout']):
                y = condition_index * 2 + case_index
                labels.append(f'{"Base" if arm == "baseline" else "REA"} {rep} · {"seen" if case == "visible" else "unseen"}')
                for x, (key, _) in enumerate(criteria):
                    value = metrics.get(f'{case}/{key}')
                    assert value in (None, 0, 1)
                    criteria_rows.append({'attempt_id': row['attempt_id'], 'fixture': family, 'arm': arm,
                                          'repetition': rep, 'input': case, 'criterion': key, 'value': value})
                    ax.add_patch(Rectangle((x-.46, y-.4), .92, .8, facecolor=PASS if value == 1 else FAIL if value == 0 else UNKNOWN))
                    ax.text(x, y, '+' if value == 1 else '×' if value == 0 else '—', ha='center', va='center',
                            color='white' if value is not None else INK, fontsize=10)
        ax.set_xlim(-.5, 8.5)
        ax.set_ylim(7.5, -.5)
        ax.set_xticks(range(9), [x[1] for x in criteria], rotation=45, ha='right')
        ax.set_yticks(range(8), labels, fontsize=10)
        ax.tick_params(length=0)
        ax.set_title(title, loc='left', fontweight='bold', pad=10)
    fig.suptitle('Which recovered behavior passed the independent checks?', fontsize=20, fontweight='bold')
    fig.text(.02, .02, '+ Pass   × Fail   — Unavailable. Missing decoders and unavailable infrastructure remain distinct in each attempt record.\nHidden-frame checks on ordinary fixtures do not replace the dedicated hidden-frame family.', fontsize=11)
    save(fig, 'final-criteria', 'Nine criteria for both visible and unseen inputs. Pixels compares the unordered RGBA collection; Order requires exact images at reference positions and can fail from a pixel mismatch. Size and FPS check manifest values; ordered image matching also checks PNG dimensions.')

    pairs = [(family, rep) for family in FAMILIES for rep in (1, 2)]
    pair_labels = [f'{NAMES[FAMILIES.index(family)]} · {rep}' for family, rep in pairs]

    def paired_resources(keys, titles, filename, caption):
        fig, axes = plt.subplots(1, len(keys), figsize=(4.3 * len(keys), 8), squeeze=False)
        fig.subplots_adjust(left=.17, right=.97, top=.84, bottom=.10, wspace=.35)
        for ax, key, title in zip(axes.flat, keys, titles):
            available = []
            for y, (family, rep) in enumerate(pairs):
                values = [projected[by_key[family, arm, rep]['attempt_id']].get(key) for arm in ['baseline', 'rea']]
                if all(v is not None for v in values):ax.plot(values, [y, y], color='#bdc6cd', lw=1.2, zorder=1)
                for arm, value, color, offset in zip(['baseline', 'rea'], values, [BASE, REA], [-.14, .14]):
                    if value is None:
                        ax.text(1.02, y+offset, 'Base N/A' if arm == 'baseline' else 'REA N/A',
                                transform=ax.get_yaxis_transform(), color=color, fontsize=8, va='center')
                    else:
                        available.append(value)
                        ax.scatter(value, y, s=40, color=color, marker='o' if arm == 'baseline' else 'D', zorder=2)
            ax.set_ylim(len(pairs)-.4, -.6)
            ax.set_yticks(range(len(pairs)), pair_labels if ax is axes.flat[0] else [])
            ax.set_xlim(0, max(available, default=1)*1.08)
            ax.grid(axis='x', alpha=.17)
            ax.set_axisbelow(True)
            ax.set_title(title, loc='left', fontsize=12, fontweight='bold', pad=12)
        axes.flat[0].scatter([], [], color=BASE, label='Baseline')
        axes.flat[0].scatter([], [], color=REA, marker='D', label='REA available')
        fig.legend(loc='upper left', bbox_to_anchor=(.17,.97), ncol=2, frameon=False)
        fig.text(.02, .025, 'Every recorded attempt is retained, including failures. Lines join the same fixture and repetition; they do not imply a causal effect.', fontsize=10)
        save(fig, filename, caption)

    paired_resources(['task_tokens_millions', 'agent_seconds', 'cost_estimate_or_reservation_usd'],
                     ['Task tokens (millions)', 'Agent seconds', 'USD estimate / reservation'], 'final-paired-resources',
                     'Paired resource measurements for all attempts, irrespective of correctness. Tokens include schemas and repeated context; elapsed time includes finalization. Cost uses the frozen runner basis and is not settled billing.')
    paired_resources(['agent_cpu_seconds', 'agent_peak_mib'], ['Local CPU seconds', 'Local peak memory (MiB)'],
                     'final-local-resources', 'Local agent container process-family accounting. Remote inference resources and per-attempt controller peak memory are unavailable. Missing values are labeled, not plotted as zero.')

    fig, ax = plt.subplots(figsize=(9, 7))
    fig.subplots_adjust(left=.27, right=.97, top=.84, bottom=.14)
    for y, (family, rep) in enumerate(pairs):
        metric = projected[by_key[family, 'rea', rep]['attempt_id']].get('rea_returned_calls')
        if metric is None:ax.text(0, y, 'Unavailable', va='center')
        else:
            ax.barh(y, metric, color=REA, height=.6)
            ax.text(metric, y, f'  {metric}', va='center')
    ax.set_yticks(range(len(pairs)), pair_labels)
    ax.invert_yaxis()
    ax.set_xlabel('Returned REA tool calls, including returned errors')
    ax.set_title('Tool availability and actual use are different observations', fontsize=17, loc='left', pad=22, fontweight='bold')
    ax.grid(axis='x', alpha=.16)
    ax.set_axisbelow(True)
    save(fig, 'final-rea-use', 'All twelve treatment attempts. A zero means REA was available but unused. Interrupted calls may exist only in Agent Lens; tool choice is not randomized within the treatment arm.')

    flat = [{k: r[k] for k in ['attempt_id', 'fixture', 'arm', 'repetition']} | projected[r['attempt_id']] for r in rows]
    for name, records in [('final-attempts.csv', flat), ('final-criteria.csv', criteria_rows)]:
        fields = list(dict.fromkeys(key for record in records for key in record))
        with (tables / name).open('w') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(records)
    (tables / 'final-summary.json').write_text(json.dumps({'arms': totals, 'changed_overall_judgments': changed,
                                                          'score_basis': summary['score_basis'], 'attempts': flat}, indent=2)+'\n')
    source = Path(__file__).with_name('publish_dashboard.py')
    (out / 'figure-manifest.json').write_text(json.dumps({'figures': manifest, 'recorded': 24, 'planned': 24,
        'comparison_sha256': hashlib.sha256(args.comparison.read_bytes()).hexdigest(),
        'projection_source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}, indent=2)+'\n')
    print(json.dumps({'figures': len(manifest), 'arms': totals, 'changed': len(changed)}))


if __name__ == '__main__':
    main()

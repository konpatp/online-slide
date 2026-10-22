#!/usr/bin/env python3
# browser-check: scratch
"""The review gate fails a cluttered chart and passes its small multiples.

Nine series in one panel with colliding end labels (the Looped Exp116 slide
the PI rejected on 2026-10-22) must be a review finding naming the panel; the
same nine series as 2x2 small multiples with at most three lines each must
pass. Runs the real reviewer (tools/review_deck.py) on a scratch deck."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from slide_templates import make_starter

GROUPS = {'k1': [3.1, 2.6, 2.2], 'k2': [3.0, 2.5, 2.1], 'k16': [2.9, 2.4, 2.0]}
FAMILIES = ('AttnRes', 'Highway', 'Specialist')


def series(index, family, depth, values, **extra):
    return {'type': 'scatter', 'mode': 'lines+markers', 'uid': f'{family}-{depth}', 'name': f'{family} {depth}',
            'x': [1, 2, 3], 'y': [v + index * .02 for v in values], **extra}


def cluttered(after):
    spec = make_starter('chart-panels', 'clutter-one-panel', '2030-01-01T00:00:00Z', after, authoring=True)
    data = []
    for f, family in enumerate(FAMILIES):
        for depth, values in GROUPS.items():
            # Endpoint labels on nearly equal values: they pile up, as on Exp116.
            data.append(series(f, family, depth, values, mode='lines+markers+text',
                               text=['', '', depth], textposition='middle right'))
    spec['components']['chart']['figure'] = {'data': data, 'layout': {
        'xaxis': {'range': [0.8, 3.6]}, 'margin': {'l': 90, 'r': 30, 't': 30, 'b': 70}}}
    return spec


def small_multiples(after):
    spec = make_starter('chart-panels', 'clutter-small-multiples', '2030-01-01T00:00:00Z', after, authoring=True)
    data, annotations, layout = [], [], {'margin': {'l': 90, 'r': 30, 't': 50, 'b': 70}, 'showlegend': False}
    domains = [([0, .46], [.58, .88]), ([.54, 1], [.58, .88]), ([0, .46], [0, .3]), ([.54, 1], [0, .3])]
    for panel, (family, (xd, yd)) in enumerate(zip(FAMILIES + ('All depths',), domains), start=1):
        suffix = '' if panel == 1 else str(panel)
        layout['xaxis' + suffix] = {'domain': xd, 'anchor': 'y' + suffix}
        layout['yaxis' + suffix] = {'domain': yd, 'anchor': 'x' + suffix}
        annotations.append({'name': f'title-{panel}', 'text': family, 'showarrow': False, 'xref': 'paper', 'yref': 'paper',
                            'x': (xd[0] + xd[1]) / 2, 'y': yd[1] + .02, 'xanchor': 'center', 'yanchor': 'bottom'})
        if panel <= len(FAMILIES):
            for depth, values in GROUPS.items():
                data.append(series(panel - 1, family, depth, values, xaxis='x' + suffix, yaxis='y' + suffix))
        else:
            data.append(series(0, 'Mean', 'all', [3.0, 2.5, 2.1], xaxis='x4', yaxis='y4'))
    layout['annotations'] = annotations
    spec['components']['chart']['figure'] = {'data': data, 'layout': layout}
    return spec


def review(root, slide, output):
    subprocess.run([sys.executable, str(ROOT / 'tools/review_deck.py'), '--root', str(root), '--slide', slide,
                    '--output', str(output)], capture_output=True, text=True, timeout=300)
    receipt = json.loads((output / 'receipt.json').read_text())
    return [f for f in receipt['findings'] if f.startswith(slide + ':')]


def main():
    with tempfile.TemporaryDirectory(prefix='slide-clutter-') as temp:
        root = Path(temp) / 'deck'
        for name in ('public', 'slides', 'data'):
            shutil.copytree(ROOT / name, root / name)
        last = sorted(json.loads(p.read_text())['id'] for p in (root / 'slides').glob('*.json'))[-1]
        bad, good = cluttered(last), small_multiples(last)
        for spec in (bad, good):
            (root / 'slides' / f"{spec['id']}.json").write_text(json.dumps(spec))
        bad_findings = review(root, bad['id'], Path(temp) / 'bad')
        good_findings = review(root, good['id'], Path(temp) / 'good')
    assert any('chart clutter' in f and '9 data series' in f and 'small multiples' in f for f in bad_findings), bad_findings
    assert any('collide' in f or 'covers a data marker' in f for f in bad_findings), bad_findings
    assert not good_findings, good_findings
    print(json.dumps({'ok': True, 'cluttered_findings': len(bad_findings), 'small_multiples_findings': 0}))


if __name__ == '__main__':
    main()

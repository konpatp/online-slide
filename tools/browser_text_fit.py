#!/usr/bin/env python3
# browser-check: scratch
"""The headline-fit estimate (slidekit/fit.py) agrees with real Chromium.

Synthetic slides carry headlines of many lengths, hyphenated words, dashes,
explicit line breaks and a font scale. The real editor renders each one; the
check counts its line boxes and requires the estimate to match every one, so a
stylesheet or font change the estimate does not follow fails here."""
import json
from pathlib import Path
import random
import shutil
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server import make_server
from slide_templates import make_starter
from slidekit.fit import headline_fit
from playwright.sync_api import sync_playwright

WORDS = ("loops steps guidance the a quality improves collapses midpoint supervision emulate "
         "free depth scale equal-compute loops-vs-steps r16h B/12 ImageNet-256 FID 50k").split()


def headlines():
    rng = random.Random(7)
    yield from ("Short", "quality improves—then every allocation collapses",
                "Highway: softly accept each four-block proposal",
                "r16h midpoint supervision: emulate, then free — the two hypotheses H1 and H2 tested",
                "First line\nsecond line", "x" * 70)
    for _ in range(54):
        yield " ".join(rng.choice(WORDS) for _ in range(rng.randint(3, 16)))


def main():
    cases = list(headlines())
    with tempfile.TemporaryDirectory(prefix='slide-fit-') as temp:
        root = Path(temp)
        shutil.copytree(ROOT / 'slides', root / 'slides')
        last = None
        for index, text in enumerate(cases):
            spec = make_starter('evidence-figure', f'fit-case-{index:03d}', '2030-01-01T00:00:00Z', after=last)
            spec['components']['headline']['text'] = text
            if index % 9 == 4:
                spec['components']['headline']['fontScale'] = 0.8
            (root / 'slides' / f'{spec["id"]}.json').write_text(json.dumps(spec))
            last = spec['id']
        http = make_server(ROOT / 'public', root / 'slides', ROOT / 'data/seed-state.json', root / 'state.json')
        threading.Thread(target=http.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={'width': 1600, 'height': 1000})
                page.goto(f'http://127.0.0.1:{http.server_address[1]}/#fit-case-000', wait_until='networkidle')
                mismatches = []
                for index, text in enumerate(cases):
                    slide = f'fit-case-{index:03d}'
                    page.evaluate('id => { location.hash = id; }', slide)
                    title = page.locator(f'.slide-canvas[data-slide-id="{slide}"] .slide-title')
                    title.wait_for()
                    measured = title.evaluate("""e => { const r = document.createRange(); r.selectNodeContents(e);
                        return new Set([...r.getClientRects()].filter(x => x.width > 0).map(x => Math.round(x.top))).size; }""")
                    scale = 0.8 if index % 9 == 4 else 1.0
                    predicted = headline_fit(text, scale=scale)['lines']
                    if predicted != measured:
                        mismatches.append({'text': text, 'scale': scale, 'browser': measured, 'estimate': predicted})
                browser.close()
        finally:
            http.shutdown(); http.server_close()
    assert not mismatches, json.dumps(mismatches, indent=1)
    print(json.dumps({'ok': True, 'cases': len(cases), 'agreement': 1.0}))


if __name__ == '__main__':
    main()

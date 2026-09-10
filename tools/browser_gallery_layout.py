#!/usr/bin/env python3
# browser-check: read-only-probe
"""Read-only gallery transition check: options cannot move controls or image slots."""
import argparse
import itertools
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--slide', required=True)
    parser.add_argument('--stylesheet', type=Path, help='local review override, never uploaded')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1920, 'height': 1080})
        errors, writes = [], []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('request', lambda r: writes.append(r.url) if r.method not in ('GET', 'HEAD', 'OPTIONS') else None)
        if args.stylesheet:
            page.route('**/styles.css*', lambda route: route.fulfill(path=str(args.stylesheet), content_type='text/css'))
        page.goto(args.url.rstrip('/') + '/?present=1#' + args.slide, wait_until='networkidle')
        groups = page.locator('.gallery-selector')
        counts = [groups.nth(i).get_by_role('button').count() for i in range(groups.count())]
        assert counts and all(counts), 'no selectable gallery found'
        assert page.locator('.gallery-cell').count(), 'gallery has no image slots'
        baseline = None
        states = []
        for choice in itertools.product(*(range(n) for n in counts)):
            for group, index in enumerate(choice):
                page.locator('.gallery-selector').nth(group).get_by_role('button').nth(index).click()
            page.wait_for_function("[...document.querySelectorAll('.gallery-cell img')].every(i=>i.complete && i.naturalWidth>0)")
            geometry = page.evaluate("""() => [...document.querySelectorAll('.gallery-selector, .gallery-selector button, .gallery-summary, .gallery-class-name, .gallery-metric, .gallery-pages, .hierarchical-gallery-view, .gallery-cell')].map(e=>{
              const r=e.getBoundingClientRect();return [r.x,r.y,r.width,r.height].map(v=>Math.round(v*10)/10);
            })""")
            if baseline is None: baseline = geometry
            assert geometry == baseline, f'gallery moved at {choice}: {geometry} != {baseline}'
            assert page.locator('.gallery-class-name').evaluate('(e)=>e.scrollHeight<=e.clientHeight+1 && e.scrollWidth<=e.clientWidth+1'), choice
            states.append(list(choice))
            if choice[-1] == 0:
                page.screenshot(path=str(args.output / ('view-' + '-'.join(map(str, choice)) + '.png')))
        assert not errors, errors
        assert not writes, writes
        browser.close()
    receipt = {'ok': True, 'states': states, 'stable_geometry': baseline, 'errors': errors, 'writes': writes}
    (args.output / 'gallery-layout.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'ok': True, 'states_verified': len(states), 'geometry_unchanged': True}))


if __name__ == '__main__':
    main()

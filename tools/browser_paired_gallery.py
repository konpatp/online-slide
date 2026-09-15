#!/usr/bin/env python3
# browser-check: read-only-probe
"""Exercise paired-image facets, source fidelity, enlargement and persistence."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from review_deck import serving


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--url')
    parser.add_argument('--state', type=Path)
    parser.add_argument('--slide', action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    results, errors, writes = [], [], []
    with serving(args) as url, sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1920, 'height': 1080})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: writes.append(request.url) if request.method == 'POST' else None)
        for sid in args.slide:
            page.goto(url+'/?present=1#'+sid, wait_until='networkidle')
            page.wait_for_function('id=>document.querySelector(".slide-canvas")?.dataset.slideId===id && document.querySelectorAll(".gallery-selector button").length>0', arg=sid)
            count = page.locator('.gallery-selector button').count()
            assert count >= 2, 'missing model options'
            baseline = None
            for index in range(count):
                page.locator('.gallery-selector button').nth(index).click()
                page.wait_for_function('[...document.querySelectorAll(".gallery-pair img")].every(i=>i.complete && i.naturalWidth>0)')
                pairs = page.locator('.gallery-pair')
                assert pairs.count() == 24
                assert page.locator('.paired-gallery-group').count() == 4
                assert page.locator('.gallery-pair img').count() == 48
                geometry = page.locator('.gallery-pair img').evaluate_all('(ns)=>ns.map(n=>{let r=n.getBoundingClientRect();return [r.x,r.y,r.width,r.height]})')
                if baseline is None:
                    baseline = geometry
                assert geometry == baseline, 'images moved on model change'
                assert page.locator('[data-fit-overflow="true"]').count() == 0
                page.screenshot(path=str(args.output/f'{sid}-{index}.png'))
                expected = pairs.first.locator('img').evaluate_all('(ns)=>ns.map(n=>[n.src,n.alt])')
                pairs.first.locator('.gallery-pair-pictures').click()
                dialog = page.get_by_role('dialog')
                assert dialog.is_visible()
                actual = dialog.locator('img').evaluate_all('(ns)=>ns.map(n=>[n.src,n.alt])')
                assert actual == expected, 'enlargement changed source pairing'
                assert dialog.locator('figcaption').all_text_contents() == ['Depth','CFG']
                page.screenshot(path=str(args.output/f'{sid}-{index}-enlarged.png'))
                page.keyboard.press('Escape')
                assert page.get_by_role('dialog').count() == 0
                assert page.url.endswith('#'+sid), 'Escape navigated away'
                # Preserve presenter selection and matched identities on refresh.
                page.reload(wait_until='networkidle')
                assert page.locator('.gallery-selector button').nth(index).get_attribute('aria-pressed') == 'true'
                assert page.locator('.gallery-pair').first.locator('img').evaluate_all('(ns)=>ns.map(n=>[n.src,n.alt])') == expected
                results.append({'slide':sid,'option':index,'pairs':24,'source_pairing':True,'stable_geometry':True})
        assert not errors and not writes, (errors,writes)
        browser.close()
    (args.output/'receipt.json').write_text(json.dumps({'ok':True,'views':results,'errors':errors,'writes':writes},indent=2)+'\n')
    print(json.dumps({'ok':True,'views':len(results)}))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
# browser-check: read-only-probe
"""Read-only physical sidebar lifecycle proof against a served chart deck."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',required=True)
    parser.add_argument('--slide',action='append',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if len(args.slide)<2: parser.error('choose at least two slides, including a chart')
    args.output.mkdir(parents=True,exist_ok=True)
    errors,writes,visits=[],[],[]
    with sync_playwright() as p:
        browser=p.chromium.launch()
        page=browser.new_page(viewport={'width':1920,'height':1080})
        page.on('pageerror',lambda e:errors.append(str(e)))
        def read_only(route):
            if route.request.method not in {'GET','HEAD','OPTIONS'}:
                writes.append(route.request.url);route.abort()
            else: route.continue_()
        page.route('**/*',read_only)
        def ready(key):
            page.wait_for_function("""id=>document.querySelector('.slide-canvas')?.dataset.slideId===id &&
              document.fonts.status==='loaded' && [...document.querySelectorAll('.native-chart')]
                .every(c=>c.dataset.chartReady==='true')""",arg=key)
        try:
            page.goto(args.url.rstrip('/')+'/#'+args.slide[0])
            ready(args.slide[0])
            for round_number in range(3):
                for key in args.slide:
                    card=page.locator('.thumb[data-id="'+key+'"] .thumb-card')
                    card.click();ready(key)
                    canvas=page.locator('.slide-canvas')
                    canvas.evaluate('c=>c.navigationSentinel=true')
                    card.click();card.click()
                    assert canvas.evaluate('c=>c.navigationSentinel') is True,'same-slide click rebuilt content'
                    visits.append(key)
                    for mode in (True,False):
                        page.locator('[data-edit-toggle]').click()
                        page.wait_for_function("mode=>document.querySelector('[data-stage]').classList.contains('edit-mode')===mode",arg=mode)
                        ready(key)
                    if round_number==2:
                        page.screenshot(path=str(args.output/(key+'.png')))
                    assert not errors,errors
            assert not writes,writes
        except Exception as error:
            errors.append(str(error))
            page.screenshot(path=str(args.output/'failure.png'))
        browser.close()
    receipt={'ok':not errors and not writes,'physicalSidebarVisits':visits,
             'sameSlideIsNoop':not errors,'editModeTransitions':2*len(visits),
             'liveWrites':len(writes),'errors':errors}
    (args.output/'navigation.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))
    return 0 if receipt['ok'] else 1


if __name__=='__main__':raise SystemExit(main())

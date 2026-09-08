#!/usr/bin/env python3
"""Read-only live editor smoke: block EVERY mutating request, query or not.

Real persistence belongs to browser_text_boxes.py's disposable server. This
probe verifies deployed controls without creating content in a curator deck.
"""
import argparse,json
from pathlib import Path
from playwright.sync_api import sync_playwright

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--url',required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    blocked=[]
    with sync_playwright() as p:
        browser=p.chromium.launch();context=browser.new_context(viewport={'width':1920,'height':1080},service_workers='block')
        def read_only(route):
            if route.request.method not in {'GET','HEAD','OPTIONS'}:
                blocked.append({'method':route.request.method,'url':route.request.url})
                route.abort()
            else:route.continue_()
        # Context-wide, all URLs: an API glob without '?' silently misses the
        # runtime-version query and can send an otherwise "read-only" probe.
        context.route('**/*',read_only)
        page=context.new_page();page.goto(args.url,wait_until='domcontentloaded')
        page.locator('[data-stage] .slide-title').wait_for()
        page.wait_for_function("document.fonts.status==='loaded'")
        page.locator('[data-edit-toggle]').click();page.locator('[data-add-text]').wait_for()
        page.screenshot(path=str(args.output/'live-editor.png'))
        page.locator('[data-add-text]').click()
        box=page.locator('[data-stage] [data-component-id^="text-box-"]').last
        box.wait_for();page.wait_for_function("document.activeElement.matches('[data-component-id^=\"text-box-\"]')")
        page.keyboard.type('First line');page.keyboard.press('Enter');page.keyboard.type('Second line')
        assert box.text_content()=='First line\nSecond line'
        page.wait_for_timeout(500)
        assert blocked,'The attempted save must have hit the read-only guard'
        receipt={'ok':True,'multilineTyping':True,'physicalAddText':True,'mutatingRequestsBlocked':blocked,'liveWrites':0}
        (args.output/'receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
        browser.close()

if __name__=='__main__':main()

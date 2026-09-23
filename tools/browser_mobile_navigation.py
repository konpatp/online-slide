#!/usr/bin/env python3
# browser-check: scratch
"""Phone navigation keeps the canvas visible; the rail never scrolls the page."""
import sys
import tempfile
import threading
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server import make_server


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--browser', choices=['chromium','webkit'], default='chromium')
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='mobile-slides-') as temp:
        http = make_server(ROOT/'public', ROOT/'slides', ROOT/'data/seed-state.json', Path(temp)/'state.json')
        threading.Thread(target=http.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                for browser_type in (getattr(p,args.browser),):
                    browser = browser_type.launch()
                    page = browser.new_page(viewport={'width':390,'height':844}, is_mobile=True, has_touch=True)
                    errors=[]
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    page.goto(f'http://127.0.0.1:{http.server_address[1]}/#mock-target-accessibility', wait_until='networkidle')
                    def contained():
                        page.wait_for_function('''() => {
                            const r=document.querySelector('.slide-canvas')?.getBoundingClientRect();
                            return r && r.width>300 && r.left>=-1 && r.right<=innerWidth+1 && r.top>=0 && r.bottom<=innerHeight+1 && Math.abs(r.width/r.height-16/9)<.01 && scrollY===0;
                        }''')
                    contained()
                    assert not page.locator('.filmstrip').is_visible()
                    page.locator('[data-slides-toggle]').tap()
                    assert page.locator('.filmstrip').is_visible()
                    page.locator('.thumb[data-id="mock-angle-evidence"] .thumb-art').tap()
                    page.wait_for_function("document.querySelector('.slide-canvas').dataset.slideId==='mock-angle-evidence'")
                    assert not page.locator('.filmstrip').is_visible()
                    contained()
                    page.reload(wait_until='networkidle'); contained()
                    page.set_viewport_size({'width':844,'height':390}); contained()
                    page.set_viewport_size({'width':740,'height':390}); contained()
                    page.locator('[data-fullscreen-toggle]').tap()
                    contained()
                    page.locator('[data-presentation-exit]').tap(force=True)
                    contained()
                    assert not errors, errors
                    browser.close()
        finally:
            http.shutdown();http.server_close()
    print(f'PASS: {args.browser} phone, reload, selection, rotation, presentation and exit')


if __name__ == '__main__': main()

#!/usr/bin/env python3
# browser-check: scratch
"""Physical typing through delayed ACKs preserves DOM/caret and durable intent."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server import make_server
from playwright.sync_api import sync_playwright


def main():
    with tempfile.TemporaryDirectory(prefix='slide-save-lifecycle-') as temporary:
        state = Path(temporary)/'state.json'
        http = make_server(ROOT/'public', ROOT/'slides', ROOT/'data/seed-state.json', state)
        threading.Thread(target=http.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={'width':1920,'height':1080})
                errors, held = [], []
                def wait_held(count):
                    deadline = time.monotonic() + 5
                    while len(held) < count and time.monotonic() < deadline:
                        page.wait_for_timeout(25)
                    assert len(held) == count, (len(held), count)
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.route('**/api/deck-state*', lambda route:
                           held.append(route) if route.request.method == 'POST' else route.continue_())
                page.goto(f'http://127.0.0.1:{http.server_address[1]}/#mock-angle-evidence')
                cell = page.locator('[data-stage] [data-component-id="random-mid"]')
                cell.wait_for()
                page.locator('[data-edit-toggle]').click()
                cell.click(); cell.fill('First')
                wait_held(1)
                cell.evaluate('element => {window.originalEditingNode = element}')
                page.keyboard.press('End'); page.keyboard.type(' second')
                page.wait_for_timeout(400)
                assert len(held) == 1, 'only one write may be outstanding'
                held[0].fulfill(response=held[0].fetch())
                wait_held(2)
                page.keyboard.type(' third')
                held[1].fulfill(response=held[1].fetch())
                # The post-ACK carry must include input even before debounce.
                wait_held(3)
                held[2].fulfill(response=held[2].fetch())
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                assert cell.evaluate('element => element===window.originalEditingNode && element===document.activeElement')
                assert cell.text_content() == 'First second third'
                assert page.evaluate('getSelection().anchorOffset') == len('First second third')
                saved = json.loads(state.read_text())
                assert saved['overlays']['mock-angle-evidence']['random-mid']['text'] == 'First second third'
                page.unroute('**/api/deck-state*')
                page.reload(); cell.wait_for()
                assert cell.text_content() == 'First second third'
                # A concurrent remote edit arriving in an intermediate ACK
                # must eventually render, even if our final ACK is otherwise
                # identical to the already-merged local snapshot.
                held.clear()
                page.route('**/api/deck-state*', lambda route:
                           held.append(route) if route.request.method == 'POST' else route.continue_())
                other = browser.new_page(viewport={'width':1920,'height':1080})
                other.goto(page.url)
                other.locator('[data-edit-toggle]').click()
                page.locator('[data-edit-toggle]').click()
                cell.fill('Local')
                wait_held(1)
                other.locator('[data-stage] [data-component-id="random-low"]').fill('Remote')
                other.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                cell.click(); page.keyboard.press('End'); page.keyboard.type(' latest')
                held[0].fulfill(response=held[0].fetch())
                wait_held(2)
                held[1].fulfill(response=held[1].fetch())
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                assert cell.text_content() == 'Local latest'
                assert page.locator('[data-stage] [data-component-id="random-low"]').text_content() == 'Remote'
                assert not errors, errors
                browser.close()
        finally:
            http.shutdown(); http.server_close()
    print('PASS delayed ACK: one writer, latest intent, unchanged live DOM/caret, reload persistence, deferred remote rendering')


if __name__ == '__main__':
    main()

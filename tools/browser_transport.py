#!/usr/bin/env python3
"""Physical editor, lazy navigation and draft recovery proof; scratch state only."""
import json
from pathlib import Path
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import server
from playwright.sync_api import sync_playwright


def main():
    with tempfile.TemporaryDirectory(prefix='slide-transport-') as temp:
        state_path = Path(temp) / 'state.json'
        http = server.make_server(ROOT/'public', ROOT/'slides', ROOT/'data/seed-state.json', state_path)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={'width': 1920, 'height': 1080})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                base = 'http://127.0.0.1:%d/' % http.server_address[1]
                first = 'mock-growth-trajectories'
                page.goto(base + '#' + first)
                page.locator('.slide-canvas[data-slide-id="%s"]' % first).wait_for()
                resources = page.evaluate('performance.getEntriesByType("resource").map(r=>r.name)')
                assert not any(name in url for url in resources for name in
                               ('plotly.min.js', 'joint-diagram.js', 'geometry-runtime.js', 'api/deck-state'))
                # Explicit sidebar actions work without enabling text editing.
                card = page.locator('.thumb[data-id="%s"]' % first)
                assert page.locator('[data-edit-toggle]').text_content() == 'Enable edit'
                with page.expect_response(lambda r: r.request.method == 'POST'):
                    card.get_by_role('button', name='Hide slide', exact=True).click()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                assert first in json.loads(state_path.read_text())['hidden']
                page.reload(); card.get_by_role('button', name='Show slide', exact=True).wait_for()
                with page.expect_response(lambda r: r.request.method == 'POST'):
                    card.get_by_role('button', name='Show slide', exact=True).click()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                before_order = json.loads(state_path.read_text())['order']
                with page.expect_response(lambda r: r.request.method == 'POST'):
                    card.get_by_role('button', name='Move later', exact=True).click()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                assert json.loads(state_path.read_text())['order'].index(first) == before_order.index(first)+1
                with page.expect_response(lambda r: r.request.method == 'POST'):
                    card.get_by_role('button', name='Move earlier', exact=True).click()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                assert json.loads(state_path.read_text())['order'] == before_order
                assert first not in json.loads(state_path.read_text())['hidden']
                # A real edit must receive a durable small ACK, not an optimistic no-op.
                page.locator('[data-edit-toggle]').click()
                headline = page.locator('.slide-title')
                headline.click()
                with page.expect_response(lambda r: r.request.method == 'POST') as ack:
                    headline.fill('Small acknowledgement, durable semantic edit')
                payload = ack.value.json()
                assert 'slides' not in payload and len(ack.value.body()) < 20000
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                saved = json.loads(state_path.read_text())
                assert saved['overlays'][first]['headline']['text'] == headline.text_content()
                page.reload()
                page.get_by_text('Small acknowledgement, durable semantic edit', exact=True).first.wait_for()

                # A slow obsolete slide response must never paint over the latest route.
                cdp = page.context.new_cdp_session(page)
                cdp.send('Network.enable')
                cdp.send('Network.emulateNetworkConditions', {'offline':False, 'latency':250,
                         'downloadThroughput':625000, 'uploadThroughput':250000})
                page.evaluate("""() => {location.hash='mock-guidance-vector-geometry';
                    setTimeout(()=>location.hash='mock-vector-construction',40); }""")
                page.locator('.slide-canvas[data-slide-id="mock-vector-construction"] .joint-paper').wait_for()
                page.wait_for_timeout(1000)
                assert page.locator('.slide-canvas').get_attribute('data-slide-id') == 'mock-vector-construction'
                cdp.send('Network.emulateNetworkConditions', {'offline':False, 'latency':0,
                         'downloadThroughput':-1, 'uploadThroughput':-1})

                # Disconnect saves only. The visible slide stays usable and a reload
                # does not silently discard or auto-apply its recoverable local draft.
                page.evaluate("location.hash='mock-growth-trajectories'")
                page.locator('.slide-canvas[data-slide-id="%s"]' % first).wait_for()
                page.locator('[data-edit-toggle]').click()
                def block_post(route):
                    if route.request.method == 'POST': route.abort()
                    else: route.continue_()
                page.route('**/api/deck-state*', block_post)
                headline.click(); headline.fill('Offline edit retained on this device')
                page.wait_for_function("document.querySelector('[data-save-state]').textContent.includes('Offline')")
                assert json.loads(state_path.read_text()) == saved
                page.reload()
                page.locator('[data-conflict-draft]').wait_for(state='visible')
                draft = page.evaluate("JSON.parse(localStorage.getItem('slidekit-conflict-draft:'+location.pathname))")
                assert draft['local']['overlays'][first]['headline']['text'] == 'Offline edit retained on this device'
                assert page.locator('.slide-title').text_content() == 'Small acknowledgement, durable semantic edit'
                assert not errors, errors
                browser.close()
                print(json.dumps({'ok':True, 'lazyLibraries':True, 'compactDurableAck':True,
                                  'navigationRace':True, 'offlineReloadDraft':True, 'liveWrites':0}))
        finally:
            http.shutdown(); http.server_close(); thread.join()


if __name__ == '__main__':
    main()

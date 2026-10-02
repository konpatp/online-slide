#!/usr/bin/env python3
# browser-check: scratch
"""Live deck updates without refresh: agent-published source edits (other
slide, current slide, new slide), another editor's saves, typing protected
until blur with local edits kept, undo kept for unaffected slides, and
reconnection after a server restart."""
import json
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server import make_server
from playwright.sync_api import sync_playwright

# THIRD has no human edits, so its source text is what the deck shows.
CURRENT, OTHER, THIRD = 'mock-growth-trajectories', 'mock-angle-evidence', 'mock-vector-construction'


def main():
    with tempfile.TemporaryDirectory(prefix='slide-live-') as temp:
        root = Path(temp); slides = root/'slides'; shutil.copytree(ROOT/'slides', slides)
        state_path = root/'state.json'

        def start(port=0):
            http = make_server(ROOT/'public', slides, ROOT/'data/seed-state.json', state_path, port=port)
            http.open_connections = []
            accept = http.process_request
            def track(request, address):
                http.open_connections.append(request); accept(request, address)
            http.process_request = track
            threading.Thread(target=http.serve_forever, daemon=True).start()
            return http

        def stop(http):
            http.shutdown()
            for connection in http.open_connections:
                try: connection.shutdown(socket.SHUT_RDWR)
                except OSError: pass
            http.server_close()

        def source(sid):
            return next(p for p in slides.glob('*.json') if json.loads(p.read_text())['id'] == sid)

        def publish(sid, text):
            path = source(sid); spec = json.loads(path.read_text())
            spec['components'][spec['headline']]['text'] = text
            path.write_text(json.dumps(spec))

        http = start(); port = http.server_address[1]
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={'width': 1600, 'height': 1000})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                url = f'http://127.0.0.1:{port}/#{CURRENT}'
                page.goto(url, wait_until='networkidle')
                page.locator(f'.slide-canvas[data-slide-id="{CURRENT}"]').wait_for()
                page.evaluate('window.__sameDocument = true')
                title = lambda: page.locator('[data-stage] .slide-title').inner_text()
                thumb = lambda sid: page.locator(f'.thumb[data-id="{sid}"]').inner_text()

                # 1. An agent publishes another slide: thumbnail updates, no reload.
                publish(OTHER, 'Agent rewrote this slide')
                page.wait_for_function("id => document.querySelector(`.thumb[data-id='${id}']`)?.innerText.includes('Agent rewrote')", arg=OTHER, timeout=6000)
                assert page.evaluate('window.__sameDocument === true'), 'the page reloaded'
                assert 'updated' in page.locator('[data-toast]').text_content()

                # 2. The slide on screen changes in place.
                publish(CURRENT, 'Live headline from an agent')
                page.wait_for_function("() => document.querySelector('[data-stage] .slide-title')?.innerText === 'Live headline from an agent'", timeout=6000)

                # 3. A new slide appears in the deck.
                count = page.locator('.thumb').count()
                spec = json.loads(source(OTHER).read_text()); spec['id'] = 'agent-new-slide'
                spec['placement'] = {'after': CURRENT}; spec['components'][spec['headline']]['text'] = 'Brand new from an agent'
                (slides/'agent-new-slide.json').write_text(json.dumps(spec))
                page.wait_for_function('n => document.querySelectorAll(".thumb").length === n + 1', arg=count, timeout=6000)
                assert 'new slide' in page.locator('[data-toast]').text_content()

                # 4. Another editor's save appears.
                other = browser.new_page(viewport={'width': 1400, 'height': 900})
                other.goto(f'http://127.0.0.1:{port}/#{OTHER}', wait_until='networkidle')
                other.locator('[data-edit-toggle]').click()
                headline = other.locator('[data-stage] .slide-title'); headline.click()
                headline.fill('Edited in another browser')
                other.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                page.wait_for_function("id => document.querySelector(`.thumb[data-id='${id}']`)?.innerText.includes('another browser')", arg=OTHER, timeout=6000)

                # 5. Typing on the current slide is never disturbed; both edits survive.
                page.locator('[data-edit-toggle]').click()
                stage_title = page.locator('[data-stage] .slide-title'); stage_title.click()
                page.keyboard.press('ControlOrMeta+End'); page.keyboard.type(' (mine)')
                stage_title.evaluate('e => { window.__typing = e; }')
                spec = json.loads(source(CURRENT).read_text()); kicker = spec.get('eyebrow')
                assert kicker, 'fixture needs an eyebrow component'
                spec['components'][kicker]['text'] = 'AGENT KICKER'; source(CURRENT).write_text(json.dumps(spec))
                page.wait_for_timeout(2500)
                assert page.evaluate('document.activeElement === window.__typing'), 'typing focus was taken'
                page.keyboard.type('!')
                assert stage_title.inner_text().endswith('(mine)!'), stage_title.inner_text()
                page.keyboard.press('Escape')
                page.wait_for_function("() => document.querySelector('[data-stage] .slide-kicker')?.innerText.includes('AGENT KICKER')", timeout=6000)
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                saved = json.loads(state_path.read_text())['overlays'][CURRENT]
                assert saved[spec['headline']]['text'].endswith('(mine)!'), saved

                # 5b. If the agent changed the very text I am editing, nothing is
                # silently merged: it is a conflict and my draft is kept.
                stage_title = page.locator('[data-stage] .slide-title'); stage_title.click()
                page.keyboard.press('ControlOrMeta+End'); page.keyboard.type(' clash')
                publish(CURRENT, 'Agent rewrote the same headline')
                page.wait_for_function("document.querySelector('[data-save-state]').textContent.startsWith('Conflict')", timeout=8000)
                draft = page.evaluate("JSON.parse(localStorage.getItem('slidekit-conflict-draft:'+location.pathname))")
                assert draft['local']['overlays'][CURRENT][spec['headline']]['text'].endswith(' clash'), draft['local']['overlays'][CURRENT]
                page.keyboard.press('Escape')
                # Resolving a conflict starts a fresh history; make one new edit.
                stage_title = page.locator('[data-stage] .slide-title'); stage_title.click()
                page.keyboard.press('ControlOrMeta+End'); page.keyboard.type(' again')
                page.keyboard.press('Escape')
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")

                # 6. Undo still reverses my edit after agents changed other slides.
                publish(THIRD, 'Another agent pass')
                page.wait_for_function("id => document.querySelector(`.thumb[data-id='${id}']`)?.innerText.includes('Another agent pass')", arg=THIRD, timeout=6000)
                assert not page.locator('[data-undo]').is_disabled(), 'undo history was discarded'

                # 7. A server restart (as every publication does) reconnects by itself.
                other.close()
                stop(http)
                publish(THIRD, 'Published across a restart')
                http = start(port)
                page.wait_for_function("id => document.querySelector(`.thumb[data-id='${id}']`)?.innerText.includes('across a restart')", arg=THIRD, timeout=15000)
                assert page.evaluate('window.__sameDocument === true')

                assert not errors, errors
                print(json.dumps({'ok': True, 'otherSlideLive': True, 'currentSlideLive': True, 'newSlideLive': True,
                    'otherEditorLive': True, 'typingProtected': True, 'sameTextConflictKept': True, 'undoKept': True, 'restartReconnects': True}))
                browser.close()
        finally:
            stop(http)


if __name__ == '__main__':
    main()

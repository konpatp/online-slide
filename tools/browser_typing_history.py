#!/usr/bin/env python3
# browser-check: scratch
"""Real-input typing reliability: IME composition never saves partial text,
typing survives saves held in flight, undo groups by pauses, redo by button,
Cmd/Ctrl+Shift+Z and Ctrl+Y, and a new edit ends the redo line."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server import make_server
from playwright.sync_api import sync_playwright

SID = 'mock-angle-evidence'


def main():
    with tempfile.TemporaryDirectory(prefix='slide-typing-') as temp:
        root = Path(temp); shutil.copytree(ROOT/'slides', root/'slides')
        state_path = root/'state.json'
        http = make_server(ROOT/'public', root/'slides', ROOT/'data/seed-state.json', state_path)
        threading.Thread(target=http.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={'width': 1600, 'height': 1000})
                errors, bodies, held = [], [], []
                hold = {'on': False}
                page.on('pageerror', lambda error: errors.append(str(error)))
                def route(r):
                    if r.request.method != 'POST': return r.continue_()
                    bodies.append(r.request.post_data or '')
                    if hold['on']: held.append(r)
                    else: r.continue_()
                page.route('**/api/deck-state*', route)
                page.goto(f'http://127.0.0.1:{http.server_address[1]}/#{SID}', wait_until='networkidle')
                page.locator(f'.slide-canvas[data-slide-id="{SID}"]').wait_for()
                page.locator('[data-edit-toggle]').click()

                def saved():
                    page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                    return json.loads(state_path.read_text())
                def text():
                    return saved()['textBoxes'][SID][key]['text']

                page.locator('[data-add-text]').click()
                box = page.locator('[data-stage] [data-component-id^="text-box-"]'); box.wait_for()
                key = box.get_attribute('data-component-id')
                page.keyboard.press('ControlOrMeta+a'); page.keyboard.type('Note')
                assert text() == 'Note'

                # 0. A save acknowledgement never re-draws the slide under the
                # editor (equal edits compared by key order used to force it).
                # Slide text (not a text box) is where editor and server order keys differently.
                title = page.locator('[data-stage] .slide-title')
                title.evaluate('e => { window.__kept = e; }')
                title.click(); page.keyboard.press('ControlOrMeta+Home')
                for _ in range(3): page.keyboard.press('Shift+ArrowRight')
                page.keyboard.press('ControlOrMeta+b'); saved()
                page.keyboard.press('ControlOrMeta+End'); page.keyboard.type('!'); saved(); page.wait_for_timeout(300)
                assert title.evaluate('e => e === window.__kept'), 'the slide was re-rendered by its own save'
                assert page.evaluate('document.activeElement === window.__kept'), 'editing focus lost on save'
                page.keyboard.press('Backspace'); saved()
                box.click()

                # 1. IME composition: partial composition text is never saved.
                cdp = page.context.new_cdp_session(page)
                page.keyboard.press('ControlOrMeta+End'); page.keyboard.type(' ')
                saved(); bodies.clear()
                for partial in ('に', 'にほ', 'にほん'):
                    cdp.send('Input.imeSetComposition', {'text': partial, 'selectionStart': len(partial), 'selectionEnd': len(partial)})
                    page.wait_for_timeout(350)                    # longer than the typing save delay
                cdp.send('Input.insertText', {'text': '日本'})
                assert text() == 'Note 日本', text()
                assert not any(fragment in body for body in bodies for fragment in ('\\u306b', 'に')), 'partial composition was saved'
                page.keyboard.type('X')
                assert text() == 'Note 日本X', 'caret stays after the composed text'

                # 2. Typing continues safely while a save is held in flight.
                hold['on'] = True
                page.keyboard.type(' quick brown fox jumps', delay=15)
                page.wait_for_timeout(300)
                assert held, 'expected a held save'
                hold['on'] = False
                for request in held: request.continue_()
                held.clear()
                assert text() == 'Note 日本X quick brown fox jumps', text()
                assert box.inner_text() == 'Note 日本X quick brown fox jumps'

                # 3. Undo groups by pauses; redo by button and both shortcuts.
                page.keyboard.press('ControlOrMeta+End'); page.wait_for_timeout(900)
                page.keyboard.type(' one'); page.wait_for_timeout(900); page.keyboard.type(' two')
                assert text().endswith(' one two')
                page.keyboard.press('ControlOrMeta+z'); assert text().endswith('jumps one'), text()
                page.keyboard.press('ControlOrMeta+z'); assert text().endswith('jumps'), text()
                redo = page.locator('[data-redo]')
                assert not redo.is_disabled()
                redo.click(); assert text().endswith('jumps one'), text()
                page.keyboard.press('ControlOrMeta+Shift+z'); assert text().endswith(' one two'), text()
                assert redo.is_disabled()
                page.keyboard.press('ControlOrMeta+z'); saved()
                page.keyboard.press('Control+y'); assert text().endswith(' one two'), text()

                # 4. A new edit ends the redo line; the browser's own undo routes here.
                page.keyboard.press('ControlOrMeta+z'); saved()
                assert not redo.is_disabled()
                box.click(); page.keyboard.press('ControlOrMeta+End'); page.keyboard.type('!')
                saved(); assert redo.is_disabled(), 'a new edit must end the redo line'
                box.evaluate("e => e.dispatchEvent(new InputEvent('beforeinput', {inputType: 'historyUndo', bubbles: true, cancelable: true}))")
                assert not text().endswith('!'), text()

                assert not errors, errors
                print(json.dumps({'ok': True, 'imeNoPartialSaves': True, 'typingDuringHeldSave': True,
                    'undoGroupsByPause': True, 'redoButtonAndShortcuts': True, 'newEditEndsRedo': True,
                    'nativeUndoRouted': True}))
                browser.close()
        finally:
            http.shutdown()


if __name__ == '__main__':
    main()

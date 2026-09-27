#!/usr/bin/env python3
# browser-check: scratch
"""Real-input rich text: character styles, colour, size, whole-object styles,
lists (Enter, exit, Tab), numbering, alignment, sanitized rich paste, one undo
per command, reload, and paragraph controls only where paragraphs make sense."""
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
PASTE = ('<meta charset="utf-8"><b style="font-weight:normal" id="docs-internal-guid-1">'
         '<p><span style="font-weight:700">Bold</span> and <span style="font-style:italic">slanted</span></p>'
         '<ul><li>First</li><li>Second<ul><li>Nested</li></ul></li></ul>'
         '<p><span style="color:#ff0000;font-family:Comic Sans MS;font-size:40px">styled</span> <a href="x">link</a>'
         '<img src="x.png"><script>bad()</script></p></b>')


def main():
    with tempfile.TemporaryDirectory(prefix='slide-rich-') as temp:
        root = Path(temp); shutil.copytree(ROOT/'slides', root/'slides')
        state_path = root/'state.json'
        http = make_server(ROOT/'public', root/'slides', ROOT/'data/seed-state.json', state_path)
        threading.Thread(target=http.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={'width': 1600, 'height': 1000})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                url = f'http://127.0.0.1:{http.server_address[1]}/#{SID}'
                page.goto(url, wait_until='networkidle')
                page.locator(f'.slide-canvas[data-slide-id="{SID}"]').wait_for()
                page.locator('[data-edit-toggle]').click()

                def saved():
                    page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                    return json.loads(state_path.read_text())

                def box_state(key):
                    return saved()['textBoxes'][SID][key]

                # A human text box with three lines.
                page.locator('[data-add-text]').click()
                box = page.locator('[data-stage] [data-component-id^="text-box-"]'); box.wait_for()
                key = box.get_attribute('data-component-id')
                page.wait_for_function("document.activeElement.matches('[data-component-id^=\"text-box-\"]')")
                page.keyboard.press('ControlOrMeta+a'); page.keyboard.type('Alpha beta gamma')
                page.keyboard.press('Enter'); page.keyboard.type('Two')
                page.keyboard.press('Enter'); page.keyboard.type('Three')
                assert box_state(key)['text'] == 'Alpha beta gamma\nTwo\nThree'

                def select_in_first_line(start, length):
                    page.keyboard.press('ControlOrMeta+Home')
                    for _ in range(start): page.keyboard.press('ArrowRight')
                    for _ in range(length): page.keyboard.press('Shift+ArrowRight')

                # 1. Italic by shortcut on "beta"; underline by button on "gamma".
                select_in_first_line(6, 4); page.keyboard.press('ControlOrMeta+i')
                assert page.locator('[data-italic]').get_attribute('aria-pressed') == 'true'
                select_in_first_line(11, 5); page.locator('[data-underline]').click()
                marks = box_state(key)['marks']
                assert {'start': 6, 'end': 10, 'italic': True} in marks and {'start': 11, 'end': 16, 'underline': True} in marks, marks
                assert box.locator('[data-text-italic="true"]').inner_text() == 'beta'

                # 2. Undo reverts only the last command.
                page.keyboard.press('ControlOrMeta+z')
                marks = box_state(key)['marks']
                assert {'start': 6, 'end': 10, 'italic': True} in marks and not any(m.get('underline') for m in marks), marks
                box.click()

                # 3. Custom colour and exact size on "Alpha"; A+ steps it further.
                select_in_first_line(0, 5)
                page.locator('[data-custom-color]').fill('#e0457b')
                size = page.locator('[data-size-field]')
                size.click(); size.fill('150'); size.press('Enter')
                marks = box_state(key)['marks']
                alpha = next(m for m in marks if m['start'] == 0)
                assert alpha.get('color') == '#e0457b' and alpha.get('size') == 1.5, marks
                box.click(); select_in_first_line(0, 5)
                page.locator('[data-font-delta="0.1"]').click()
                assert next(m for m in box_state(key)['marks'] if m['start'] == 0)['size'] == 1.6
                assert page.locator('[data-size-field]').input_value() == '160'

                # 4. Lists: shortcut, Enter continues, Enter on empty ends, Tab indents.
                box.click(); page.keyboard.press('ControlOrMeta+End')
                page.keyboard.press('Shift+ArrowUp')
                page.keyboard.press('ControlOrMeta+Shift+8')
                assert box_state(key)['paragraphs'] == [{}, {'list': 'bullet'}, {'list': 'bullet'}]
                markers = box.locator('.text-line').evaluate_all("ls=>ls.map(l=>l.dataset.marker||'')")
                assert markers == ['', '•', '•'], markers
                page.keyboard.press('ControlOrMeta+End'); page.keyboard.press('Enter'); page.keyboard.type('Four')
                state = box_state(key)
                assert state['text'].endswith('Three\nFour') and state['paragraphs'][-1] == {'list': 'bullet'}, state
                page.keyboard.press('Enter'); page.keyboard.press('Enter')
                assert box_state(key)['paragraphs'][-1] == {}, 'Enter on an empty item ends the list'
                page.keyboard.press('Backspace')
                page.keyboard.press('ControlOrMeta+End'); page.keyboard.press('Tab')
                assert box_state(key)['paragraphs'][-1] == {'list': 'bullet', 'level': 1}
                assert box.locator('.text-line').last.get_attribute('data-marker') == '◦'
                page.keyboard.press('Shift+Tab')
                assert box_state(key)['paragraphs'][-1] == {'list': 'bullet'}

                # 5. Numbering and alignment from the Paragraph menu.
                page.keyboard.press('ControlOrMeta+End'); page.keyboard.press('Shift+ArrowUp'); page.keyboard.press('Shift+ArrowUp')
                page.locator('[data-paragraph-toggle]').click()
                page.get_by_role('button', name='Numbered list', exact=True).click()
                markers = box.locator('.text-line').evaluate_all("ls=>ls.map(l=>l.dataset.marker||'')")
                assert markers[1:] == ['1.', '2.', '3.'], markers
                box.click(); page.keyboard.press('ControlOrMeta+Home')
                page.locator('[data-paragraph-toggle]').click()
                page.get_by_role('button', name='Center text', exact=True).click()
                assert box_state(key)['paragraphs'][0] == {'align': 'center'}
                assert all('align' not in p for p in box_state(key)['paragraphs'][1:]), 'alignment only on the caret line'
                assert box.locator('.text-line').first.evaluate('e=>getComputedStyle(e).textAlign') == 'center'

                # 6. Rich paste keeps bold/italic/lists; drops colour, font, size, links, images, scripts.
                box.click(); page.keyboard.press('ControlOrMeta+End'); page.keyboard.press('Enter')
                page.keyboard.press('Enter')                   # leave the numbered list first
                box.evaluate("""(el, html) => {const data = new DataTransfer(); data.setData('text/html', html);
                  data.setData('text/plain', 'fallback'); el.dispatchEvent(new ClipboardEvent('paste', {clipboardData: data, bubbles: true, cancelable: true}));}""", PASTE)
                state = box_state(key)
                tail = state['text'].split('\n')[-5:]
                assert tail == ['Bold and slanted', 'First', 'Second', 'Nested', 'styled link'], tail
                assert state['paragraphs'][-4:-1] == [{'list': 'bullet'}, {'list': 'bullet'}, {'list': 'bullet', 'level': 1}], state['paragraphs']
                offset = state['text'].index('Bold and slanted')
                assert {'start': offset, 'end': offset + 4, 'bold': True} in state['marks']
                assert any(m.get('italic') and m['start'] == offset + 9 for m in state['marks'])
                styled_at = state['text'].index('styled')
                assert not any(m['start'] <= styled_at < m['end'] and ('color' in m or 'size' in m) for m in state['marks'])
                assert 'bad()' not in state['text'] and 'fallback' not in state['text']

                # 7. Whole-object styles: object selected, no text focused.
                page.keyboard.press('Escape')
                assert not page.evaluate('document.activeElement.isContentEditable')
                page.locator('[data-color="#0f9d78"]').click()
                assert box_state(key)['color'] == '#0f9d78'

                # 8. Everything survives a reload exactly.
                before = saved()['textBoxes'][SID][key]
                page.reload(wait_until='networkidle'); box.wait_for()
                assert box.locator('[data-text-italic="true"]').count() >= 1
                assert box.locator('.text-line[data-list="number"]').count() == 3
                assert box.locator('.text-line').first.evaluate('e=>getComputedStyle(e).textAlign') == 'center'
                assert json.loads(state_path.read_text())['textBoxes'][SID][key] == before

                # 9. Paragraph controls only where lines are blocks; no font picker.
                page.locator('[data-edit-toggle]').click()
                # The first table cell sits clear of the text box made above.
                cell = page.locator('[data-stage] [data-table-cell] .semantic-component').first; cell.click()
                assert page.locator('[data-paragraph-toggle]').is_disabled()
                assert not page.locator('[data-bold]').is_disabled()
                assert page.locator('[data-font-family], select[aria-label*="font" i]').count() == 0

                assert not errors, errors
                print(json.dumps({'ok': True, 'italicUnderline': True, 'undoOneCommand': True, 'colourAndSize': True,
                    'listsEnterExitTab': True, 'numberingAlignment': True, 'sanitizedRichPaste': True,
                    'wholeObjectStyle': True, 'reloadExact': True, 'paragraphControlsScoped': True}))
                browser.close()
        finally:
            http.shutdown()


if __name__ == '__main__':
    main()

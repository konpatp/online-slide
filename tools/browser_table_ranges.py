#!/usr/bin/env python3
# browser-check: scratch
"""Real-input table ranges: drag across cells vs text selection inside one,
Shift-click, row/column/table selection, batch bold and colour, clearing,
deleting spanned rows, each as one undo step; Escape ends the range."""
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
    with tempfile.TemporaryDirectory(prefix='slide-ranges-') as temp:
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
                page.goto(f'http://127.0.0.1:{http.server_address[1]}/#{SID}', wait_until='networkidle')
                page.locator('[data-stage] [data-native-table]').first.wait_for()
                page.locator('[data-edit-toggle]').click()

                def saved():
                    page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                    return json.loads(state_path.read_text())

                def cell(row, col):
                    return page.locator(f'[data-stage] [data-native-table] [data-table-row-index="{row}"][data-table-column-index="{col}"]').first

                def cid(row, col):
                    return cell(row, col).locator('.semantic-component').get_attribute('data-component-id')

                def centre(row, col):
                    b = cell(row, col).bounding_box(); return b['x'] + b['width'] / 2, b['y'] + b['height'] / 2

                def drag(a, b):
                    page.mouse.move(*centre(*a)); page.mouse.down()
                    page.mouse.move(*centre(*b), steps=8); page.mouse.up()

                ranged = lambda: page.locator('[data-stage] .table-range-cell').count()
                rows = page.locator('[data-stage] [data-native-table] tbody tr').count()
                assert rows >= 3, rows

                # 1. Dragging inside one cell selects its text, not a range.
                b = cell(0, 0).bounding_box()
                page.mouse.move(b['x'] + 6, b['y'] + b['height'] / 2); page.mouse.down()
                page.mouse.move(b['x'] + b['width'] * .7, b['y'] + b['height'] / 2, steps=5); page.mouse.up()
                assert ranged() == 0 and page.evaluate('getSelection().toString().length') > 0

                # 2. Dragging across cells selects the rectangle between them. The
                # table tools appearing in the toolbar must not move the slide.
                canvas = page.locator('.slide-canvas').bounding_box()
                drag((0, 1), (1, 2))
                assert page.locator('.slide-canvas').bounding_box() == canvas, 'the toolbar moved the slide'
                assert ranged() == 4, ranged()
                assert page.locator('[data-selected-component]').text_content().startswith('4 cells selected')
                assert page.evaluate('getSelection().toString()') == '', 'a range is not a text selection'

                # 3. Bold and colour apply to every cell; each is one undo step.
                ids = [cid(r, c) for r in (0, 1) for c in (1, 2)]
                page.keyboard.press('ControlOrMeta+b'); state = saved()
                for key in ids:
                    overlay = state['overlays'][SID][key]
                    assert overlay['marks'] == [{'start': 0, 'end': len(overlay['text']), 'bold': True}], (key, overlay)
                page.locator('[data-color="#d46b32"]').click(); state = saved()
                assert all(state['overlays'][SID][key]['color'] == '#d46b32' for key in ids)
                page.keyboard.press('ControlOrMeta+z'); state = saved()
                assert all('color' not in state['overlays'][SID][key] for key in ids)
                page.keyboard.press('ControlOrMeta+z'); state = saved()
                assert all(not state['overlays'].get(SID, {}).get(key, {}).get('marks') for key in ids)

                # 4. Escape ends a range; a plain click on a cell ends it too.
                drag((0, 1), (1, 2)); page.keyboard.press('Escape')
                assert ranged() == 0
                drag((0, 1), (1, 2)); cell(2, 1).click()
                assert ranged() == 0

                # 5. Shift-click extends from the selected cell.
                cell(0, 1).click()
                page.keyboard.down('Shift'); cell(2, 2).click(); page.keyboard.up('Shift')
                assert ranged() == 6, ranged()

                # 6. Whole row, column and table from the toolbar.
                cell(1, 1).click()
                page.locator('[data-table-select="row"]').click()
                columns = page.locator('[data-stage] [data-native-table] thead th').count()
                assert ranged() == columns, (ranged(), columns)
                cell(1, 1).click(); page.locator('[data-table-select="column"]').click()
                assert ranged() == rows + 1
                cell(1, 1).click(); page.locator('[data-table-select="table"]').click()
                assert ranged() == (rows + 1) * columns

                # 7. Delete clears the selected cells; one undo restores them.
                drag((0, 1), (1, 2))
                texts = {key: page.locator(f'[data-stage] [data-component-id="{key}"]').inner_text() for key in ids}
                page.keyboard.press('Delete'); state = saved()
                assert all(state['overlays'][SID][key]['text'] == '' for key in ids)
                page.keyboard.press('ControlOrMeta+z'); saved()
                assert all(page.locator(f'[data-stage] [data-component-id="{key}"]').inner_text() == texts[key] for key in ids)

                # 7b. Clearing the whole table saves (math cells included) and undoes.
                cell(0, 1).click(); page.locator('[data-table-select="table"]').click()
                page.keyboard.press('Delete'); saved()
                assert page.locator('[data-save-state]').text_content() == 'Saved'
                page.keyboard.press('ControlOrMeta+z'); saved()
                assert all(page.locator(f'[data-stage] [data-component-id="{key}"]').inner_text() == texts[key] for key in ids)

                # 8. Row − removes every row the range spans, as one step.
                before = page.locator('[data-stage] [data-native-table] tbody tr').count()
                drag((0, 1), (1, 1))
                page.locator('[data-table-action="row-delete"]').click(); saved()
                assert page.locator('[data-stage] [data-native-table] tbody tr').count() == before - 2
                page.keyboard.press('ControlOrMeta+z'); saved()
                assert page.locator('[data-stage] [data-native-table] tbody tr').count() == before

                assert not errors, errors
                print(json.dumps({'ok': True, 'dragInsideSelectsText': True, 'dragAcrossSelectsRange': True,
                    'batchBoldColourOneUndoEach': True, 'escapeAndClickEndRange': True, 'shiftClickExtends': True,
                    'rowColumnTable': True, 'deleteClearsWithUndo': True, 'rowSpanDelete': True}))
                browser.close()
        finally:
            http.shutdown()


if __name__ == '__main__':
    main()

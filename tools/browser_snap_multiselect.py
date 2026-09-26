#!/usr/bin/env python3
# browser-check: scratch
"""Real-input snapping, multi-selection, box selection, group move/resize,
align, distribute, group nudge, select-all and group delete with one undo."""
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server import make_server
from slide_templates import make_starter
from playwright.sync_api import sync_playwright

SID = 'snap-lab'
BOXES = {'a': (200, 700), 'b': (600, 700), 'c': (1300, 740)}


def main():
    with tempfile.TemporaryDirectory(prefix='slide-snap-') as temp:
        root = Path(temp); shutil.copytree(ROOT/'slides', root/'slides')
        spec = make_starter('section-divider', SID, datetime.now(timezone.utc).isoformat())
        (root/'slides'/f'{SID}.json').write_text(json.dumps(spec))
        state = json.loads((ROOT/'data/seed-state.json').read_text())
        state['textBoxes'] = {SID: {f'text-box-{name}': {'text': name.upper(), 'marks': [],
            'region': {'x': x, 'y': y, 'width': 220, 'height': 90}} for name, (x, y) in BOXES.items()}}
        state_path = root/'state.json'; state_path.write_text(json.dumps(state))
        http = make_server(ROOT/'public', root/'slides', ROOT/'data/seed-state.json', state_path)
        threading.Thread(target=http.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={'width': 1600, 'height': 1000})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{http.server_address[1]}/#{SID}', wait_until='networkidle')
                page.locator(f'.slide-canvas[data-slide-id="{SID}"]').wait_for()
                page.locator('[data-edit-toggle]').click()
                page.wait_for_timeout(400)

                def saved():
                    page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")

                def scale():
                    return page.locator('.slide-canvas').evaluate('c=>c.getBoundingClientRect().width/1920')

                def element(name):
                    return page.locator(f'[data-stage] [data-component-id="text-box-{name}"]')

                def box(name):
                    return element(name).evaluate("""e=>{const c=e.closest('.slide-canvas').getBoundingClientRect(),
                      r=e.getBoundingClientRect(),s=c.width/1920;
                      return {x:(r.left-c.left)/s,y:(r.top-c.top)/s,width:r.width/s,height:r.height/s}}""")

                def screen(x, y):
                    c = page.locator('.slide-canvas').bounding_box(); s = scale()
                    return c['x'] + x * s, c['y'] + y * s

                def keys():
                    return page.evaluate("[...document.querySelectorAll('.transform-member')].length || document.querySelectorAll('.transform-frame').length")

                def press(name, dx=0, dy=0, alt=False, shift=False, during=None):
                    """Press on a box (not its text editing), optionally drag in canonical px."""
                    b = box(name); x, y = screen(b['x'] + 8, b['y'] + 8); s = scale()
                    page.mouse.move(x, y)
                    for key, held in (('Alt', alt), ('Shift', shift)):
                        if held: page.keyboard.down(key)
                    page.mouse.down()
                    if dx or dy:
                        page.mouse.move(x + dx * s * .5, y + dy * s * .5, steps=4)
                        page.mouse.move(x + dx * s, y + dy * s, steps=4)
                        if during: during()
                    page.mouse.up()
                    for key, held in (('Shift', shift), ('Alt', alt)):
                        if held: page.keyboard.up(key)

                def undo():
                    page.keyboard.press('Escape'); page.keyboard.press('ControlOrMeta+z'); saved()

                close = lambda a, b, t=.6: abs(a - b) <= t
                seen = {}

                # 1. Moving near the slide centre snaps to it and shows a guide.
                a0 = box('a')
                def look_for_centre_guide():
                    seen['guide'] = page.evaluate("[...document.querySelectorAll('.transform-guide-x')].length")
                press('a', 960 - (a0['x'] + 110) - 3, 0, during=look_for_centre_guide)
                saved()
                assert close(box('a')['x'] + 110, 960), box('a')
                assert seen['guide'] >= 1, 'no centre guide while dragging'
                assert page.locator('.transform-guides').count() == 0, 'guides remain after the drop'
                undo(); assert close(box('a')['x'], a0['x'])

                # 2. Alt disables snapping.
                press('a', 960 - (a0['x'] + 110) - 3, 0, alt=True); saved()
                assert close(box('a')['x'] + 110, 957, 1.2), box('a')
                undo()

                # 3. Shift-click builds a selection; a plain click collapses it.
                press('a'); press('b', shift=True); press('c', shift=True)
                assert page.locator('.transform-frame-group').count() == 1 and keys() == 3
                assert page.locator('[data-selected-component]').text_content().startswith('3 objects selected')
                press('b', shift=True)
                assert keys() == 2
                press('a')
                assert page.locator('.transform-frame-group').count() == 0 and page.locator('.transform-frame').count() == 1

                # 4. A box drawn on empty space selects what it fully encloses.
                page.keyboard.press('Escape')
                x0, y0 = screen(150, 650); x1, y1 = screen(900, 830)
                page.mouse.move(x0, y0); page.mouse.down(); page.mouse.move(x1, y1, steps=6)
                assert page.locator('.transform-marquee').count() == 1
                page.mouse.up()
                assert keys() == 2 and page.locator('.transform-marquee').count() == 0

                # 5. Dragging one member moves the whole group; one undo restores it.
                before = {name: box(name) for name in BOXES}
                press('a', 60, -40, alt=True); saved()
                for name in 'ab':
                    assert close(box(name)['x'], before[name]['x'] + 60, 1) and close(box(name)['y'], before[name]['y'] - 40, 1), name
                assert close(box('c')['x'], before['c']['x'])
                undo()
                assert all(close(box(n)['x'], before[n]['x']) and close(box(n)['y'], before[n]['y']) for n in BOXES)

                # 6. Arrow keys move the group; a burst is one undo step.
                press('a'); press('b', shift=True)
                for _ in range(3): page.keyboard.press('ArrowRight')
                saved()
                assert close(box('a')['x'], before['a']['x'] + 3) and close(box('b')['x'], before['b']['x'] + 3)
                page.keyboard.press('ControlOrMeta+z'); saved()
                assert close(box('a')['x'], before['a']['x']) and close(box('b')['x'], before['b']['x'])

                # 7. Align top from the Arrange menu; one undo restores both.
                press('a'); press('c', shift=True)
                page.locator('[data-arrange-toggle]').click()
                page.get_by_role('button', name='Align top', exact=True).click(); saved()
                assert close(box('c')['y'], box('a')['y']) and close(box('a')['y'], before['a']['y'])
                # After a toolbar command, arrow keys still move the selection
                # (found by the random test: they used to change slides).
                page.keyboard.press('ArrowRight'); saved()
                assert page.locator('.slide-canvas').get_attribute('data-slide-id') == SID
                assert close(box('c')['x'], before['c']['x'] + 1) and close(box('a')['x'], before['a']['x'] + 1)
                page.keyboard.press('ControlOrMeta+z'); saved()
                undo(); assert close(box('c')['y'], before['c']['y']) and close(box('c')['x'], before['c']['x'])

                # 8. Distribute horizontally: equal gaps, outer objects fixed.
                press('a'); press('b', shift=True); press('c', shift=True)
                page.locator('[data-arrange-toggle]').click()
                page.get_by_role('button', name='Distribute horizontally', exact=True).click(); saved()
                a, b, c = box('a'), box('b'), box('c')
                assert close(b['x'] - (a['x'] + a['width']), c['x'] - (b['x'] + b['width']), 1), (a, b, c)
                assert close(a['x'], before['a']['x']) and close(c['x'], before['c']['x'])
                undo()

                # 9. Equal spacing between neighbours snaps and is labelled.
                page.keyboard.press('Escape')
                target = (box('a')['x'] + 220 + box('c')['x'] - 220) / 2
                def look_for_spacing():
                    seen['spacing'] = page.evaluate("[...document.querySelectorAll('.transform-spacing-x')].map(e=>e.dataset.gap)")
                press('b', target - box('b')['x'] - 3, 0, during=look_for_spacing); saved()
                assert close(box('b')['x'], target), (box('b'), target)
                assert len(seen['spacing']) == 2 and seen['spacing'][0] == seen['spacing'][1], seen
                undo()

                # 10. Resizing a group scales every member through the union.
                press('a'); press('b', shift=True)
                handle = page.get_by_role('button', name='Resize selection', exact=True).bounding_box()
                s = scale(); a1, b1 = box('a'), box('b')
                union_width = b1['x'] + b1['width'] - a1['x']
                page.keyboard.down('Alt'); page.mouse.move(handle['x'] + 6, handle['y'] + 6); page.mouse.down()
                page.mouse.move(handle['x'] + 6 + union_width * .5 * s, handle['y'] + 6, steps=6); page.mouse.up(); page.keyboard.up('Alt')
                saved()
                assert close(box('a')['x'], a1['x'], 1) and close(box('a')['width'], a1['width'] * 1.5, 2), box('a')
                assert close(box('b')['x'], a1['x'] + (b1['x'] - a1['x']) * 1.5, 2), box('b')
                undo()

                # 11. Select all, then delete everything as one undoable change.
                page.keyboard.press('Escape'); page.locator('[data-stage]').focus()
                page.keyboard.press('ControlOrMeta+a')
                selectable = page.evaluate("new Set([...document.querySelectorAll('[data-stage] [data-transform-target]')].map(e=>e.dataset.transformTarget)).size")
                assert keys() == selectable >= 4, (keys(), selectable)
                page.keyboard.press('Delete'); saved()
                assert all(not element(n).is_visible() for n in BOXES)
                page.keyboard.press('ControlOrMeta+z'); saved()
                assert all(element(n).is_visible() for n in BOXES)
                final = json.loads(state_path.read_text())
                assert all(not box_.get('deleted') for box_ in final['textBoxes'][SID].values())

                assert not errors, errors
                print(json.dumps({'ok': True, 'snapCentreWithGuide': True, 'altDisablesSnap': True,
                    'shiftClickAndCollapse': True, 'boxSelect': True, 'groupMoveSingleUndo': True,
                    'groupNudge': True, 'alignTop': True, 'distribute': True, 'equalSpacingSnap': seen['spacing'],
                    'groupResize': True, 'selectAllDeleteUndo': True}))
                browser.close()
        finally:
            http.shutdown()


if __name__ == '__main__':
    main()

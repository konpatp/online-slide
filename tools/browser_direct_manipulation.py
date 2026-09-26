#!/usr/bin/env python3
# browser-check: scratch
"""Real-input direct manipulation: click vs drag, eight handles, proportional
resize, nudging, undo, Escape, diagram boxes, constant handle size, reload."""
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

HANDLES = {'nw': 'top-left', 'n': 'top', 'ne': 'top-right', 'e': 'right',
           'se': None, 's': 'bottom', 'sw': 'bottom-left', 'w': 'left'}


def main():
    with tempfile.TemporaryDirectory(prefix='slide-direct-manipulation-') as temp:
        root = Path(temp)
        shutil.copytree(ROOT/'slides', root/'slides')
        state_path = root/'state.json'
        http = make_server(ROOT/'public', root/'slides', ROOT/'data/seed-state.json', state_path)
        threading.Thread(target=http.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={'width': 1600, 'height': 1000})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                url = f'http://127.0.0.1:{http.server_address[1]}/'
                sid = 'mock-angle-evidence'
                page.goto(url + '#' + sid, wait_until='networkidle')
                page.locator(f'.slide-canvas[data-slide-id="{sid}"]').wait_for()
                page.locator('[data-edit-toggle]').click()

                def saved():
                    page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")

                def saved_state():
                    saved()
                    return json.loads(state_path.read_text())

                def scale():
                    return page.locator('.slide-canvas').evaluate('c=>c.getBoundingClientRect().width/1920')

                def box(locator):
                    """Painted box in canonical slide pixels."""
                    return locator.evaluate("""e=>{const c=e.closest('.slide-canvas').getBoundingClientRect(),
                      r=e.getBoundingClientRect(),s=c.width/1920;
                      return {x:(r.left-c.left)/s,y:(r.top-c.top)/s,width:r.width/s,height:r.height/s}}""")

                def drag(x, y, dx, dy, shift=False):
                    page.mouse.move(x, y)
                    if shift: page.keyboard.down('Shift')
                    page.mouse.down()
                    page.mouse.move(x + dx, y + dy, steps=6)
                    page.mouse.up()
                    if shift: page.keyboard.up('Shift')

                def close(a, b, tolerance=2.5):
                    return abs(a - b) <= tolerance

                title = page.locator('[data-stage] .slide-title')
                frame = page.locator('.transform-frame')

                # 1. A click edits text at the pointer and moves nothing.
                t0 = box(title)
                r = title.bounding_box()
                page.mouse.click(r['x'] + 30, r['y'] + r['height'] / 2)
                page.wait_for_function("document.activeElement.classList.contains('slide-title')")
                assert page.evaluate('getSelection().rangeCount && getSelection().getRangeAt(0).collapsed')
                assert frame.count() == 1, 'clicked text shows its frame'
                assert box(title) == t0 and title.get_attribute('data-component-id')

                # 2. While editing, a drag selects words instead of moving.
                drag(r['x'] + 20, r['y'] + r['height'] / 2, 120, 0)
                assert page.evaluate('getSelection().toString().length') > 2
                assert close(box(title)['x'], t0['x'], .5), 'text selection moved the object'

                # 3. Escape leaves the text; the object stays selected; arrows nudge it.
                page.keyboard.press('Escape')
                assert not page.evaluate("document.activeElement.isContentEditable")
                before_nudge = box(title)
                for _ in range(3): page.keyboard.press('ArrowRight')
                page.keyboard.press('Shift+ArrowDown')
                nudged = box(title)
                assert close(nudged['x'], before_nudge['x'] + 3, .6) and close(nudged['y'], before_nudge['y'] + 10, .6), (before_nudge, nudged)
                assert page.locator('.slide-canvas').get_attribute('data-slide-id') == sid, 'arrow nudged, not navigated'
                saved_state()
                # A burst of nudges is one undo step.
                page.keyboard.press('ControlOrMeta+z')
                assert close(box(title)['x'], before_nudge['x'], .6) and close(box(title)['y'], before_nudge['y'], .6)
                saved()

                # 4. Escape again deselects; arrows then change slides as before.
                page.keyboard.press('Escape')
                assert frame.count() == 0
                page.keyboard.press('ArrowRight')
                page.wait_for_function("document.querySelector('.slide-canvas').dataset.slideId!==%s" % json.dumps(sid))
                page.keyboard.press('ArrowLeft')
                page.locator(f'.slide-canvas[data-slide-id="{sid}"]').wait_for()
                title = page.locator('[data-stage] .slide-title')

                # 5. Dragging text that is not being edited moves the whole object.
                t0 = box(title); r = title.bounding_box(); s = scale()
                drag(r['x'] + 40, r['y'] + r['height'] / 2, 90, 60)
                moved = box(title)
                assert close(moved['x'], t0['x'] + 90 / s) and close(moved['y'], t0['y'] + 60 / s), (t0, moved)
                assert not page.evaluate("document.activeElement.isContentEditable"), 'a drag must not start typing'
                state = saved_state()
                region = state['overlays'][sid][title.get_attribute('data-component-id')]['region']
                assert region['width'] > 0

                # 6. Every handle drags its own edges; the opposite edges stay put.
                for handle, name in HANDLES.items():
                    label = 'Resize text region' + ('' if name is None else ' from ' + name)
                    before = box(title)
                    control = page.get_by_role('button', name=label, exact=True)
                    c = control.bounding_box()
                    dx = -30 if 'w' in handle else 30 if 'e' in handle else 0
                    dy = -20 if 'n' in handle else 20 if 's' in handle else 0
                    drag(c['x'] + c['width'] / 2, c['y'] + c['height'] / 2, dx, dy)
                    after = box(title); s = scale()
                    right, bottom = before['x'] + before['width'], before['y'] + before['height']
                    # Edges follow the pointer but never leave the slide.
                    if 'w' in handle: assert close(after['x'] + after['width'], right) and close(after['x'], max(0, before['x'] + dx / s)), (handle, before, after)
                    if 'e' in handle: assert close(after['x'], before['x']) and close(after['width'], min(1920 - before['x'], before['width'] + dx / s)), (handle, before, after)
                    if 'n' in handle: assert close(after['y'] + after['height'], bottom) and close(after['y'], max(0, before['y'] + dy / s)), (handle, before, after)
                    if 's' in handle: assert close(after['y'], before['y']) and close(after['height'], min(1080 - before['y'], before['height'] + dy / s)), (handle, before, after)
                    if handle in 'ns': assert close(after['width'], before['width']), (handle, before, after)
                    if handle in 'ew': assert close(after['height'], before['height']), (handle, before, after)
                    saved()

                # 7. Shift keeps proportions.
                before = box(title)
                c = page.get_by_role('button', name='Resize text region', exact=True).bounding_box()
                drag(c['x'] + c['width'] / 2, c['y'] + c['height'] / 2, -160, -5, shift=True)
                after = box(title)
                assert abs(after['width'] / after['height'] - before['width'] / before['height']) < .03, (before, after)
                assert after['width'] < before['width'] - 60, (before, after)
                state = saved_state()

                # 8. Handles stay the same size on screen at any zoom.
                sizes = []
                for viewport in ({'width': 1600, 'height': 1000}, {'width': 1100, 'height': 760}):
                    page.set_viewport_size(viewport); page.wait_for_timeout(250)
                    handle = page.get_by_role('button', name='Resize text region', exact=True).bounding_box()
                    sizes.append(round(handle['width'], 1))
                assert max(sizes) - min(sizes) < 1 and 10 <= sizes[0] <= 16, sizes
                page.set_viewport_size({'width': 1600, 'height': 1000}); page.wait_for_timeout(250)

                # 9. Reload keeps the geometry exactly.
                geometry = box(title)
                page.reload(wait_until='networkidle')
                title = page.locator('[data-stage] .slide-title'); title.wait_for()
                page.wait_for_timeout(300)
                reloaded = box(title)
                assert all(close(geometry[k], reloaded[k], 1) for k in geometry), (geometry, reloaded)
                assert json.loads(state_path.read_text())['overlays'] == state['overlays']

                # 9b. Typing then immediately dragging: the typing save timer must
                # not cut the drag's undo step short (found by the random test).
                if page.locator('[data-edit-toggle]').inner_text() == 'Enable edit':
                    page.locator('[data-edit-toggle]').click()
                title.click(); page.keyboard.press('End'); page.keyboard.type(' now')
                typed = title.inner_text()
                before = box(title)
                c = page.get_by_role('button', name='Resize text region from bottom', exact=True).bounding_box()
                page.mouse.move(c['x'] + c['width'] / 2, c['y'] + c['height'] / 2); page.mouse.down()
                for step in range(12):
                    page.mouse.move(c['x'] + c['width'] / 2, c['y'] + c['height'] / 2 + 3 * (step + 1)); page.wait_for_timeout(45)
                page.mouse.up(); saved()
                assert box(title)['height'] > before['height'] + 20
                page.keyboard.press('ControlOrMeta+z'); saved()
                assert close(box(title)['height'], before['height'], 1) and title.inner_text() == typed, (before, box(title))
                page.keyboard.press('ControlOrMeta+z'); saved()
                assert not title.inner_text().endswith(' now')
                assert 'Cannot undo' not in (page.locator('[data-toast]').text_content() or '')

                # 10. A diagram box moves and resizes as one object; its links follow.
                page.goto(url + '#mock-vector-construction')
                if page.locator('[data-edit-toggle]').inner_text() == 'Enable edit':
                    page.locator('[data-edit-toggle]').click()
                block = page.locator('[data-diagram-node-id="teacher-node"]')
                node = page.locator('.joint-element[model-id="teacher-node"]'); node.wait_for()
                page.wait_for_timeout(400)
                n0 = box(block); r = node.bounding_box(); s = scale()
                link_before = page.locator('.joint-link[model-id="query-to-teacher"] path').first.get_attribute('d')
                drag(r['x'] + 8, r['y'] + 8, 50, 40)
                n1 = box(block)
                assert close(n1['x'], n0['x'] + 50 / s, 4) and close(n1['y'], n0['y'] + 40 / s, 4), (n0, n1)
                assert page.locator('.joint-link[model-id="query-to-teacher"] path').first.get_attribute('d') != link_before
                state = saved_state()
                geometry = state['objects']['mock-vector-construction']['teacher-node']
                assert geometry['kind'] == 'diagram-node' and geometry['x'] > 0
                c = page.get_by_role('button', name='Resize diagram box', exact=True).bounding_box()
                drag(c['x'] + c['width'] / 2, c['y'] + c['height'] / 2, 40, 30)
                n2 = box(block)
                assert n2['width'] > n1['width'] + 10 and n2['height'] > n1['height'] + 10, (n1, n2)
                assert close(n2['x'], n1['x'], 4) and close(n2['y'], n1['y'], 4)
                saved()
                # Its text still edits on click.
                label = block.locator('.node-label')
                lr = label.bounding_box()
                page.mouse.click(lr['x'] + lr['width'] / 2, lr['y'] + lr['height'] / 2)
                page.wait_for_function("document.activeElement.classList.contains('node-label')")
                assert close(box(block)['x'], n2['x'], 1)

                assert not errors, errors
                print(json.dumps({'ok': True, 'clickEdits': True, 'dragSelectsWhileEditing': True,
                    'nudgeAndSingleUndo': True, 'escapeDeselects': True, 'bodyDragMoves': True,
                    'eightHandles': True, 'shiftProportional': True, 'constantHandleSize': sizes,
                    'reloadExact': True, 'diagramBoxMoveResize': True}))
                browser.close()
        finally:
            http.shutdown()


if __name__ == '__main__':
    main()

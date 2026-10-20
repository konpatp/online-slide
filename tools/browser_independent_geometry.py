#!/usr/bin/env python3
# browser-check: scratch
"""Moving or resizing one object never moves or resizes another (PI 2026-10-19).

Every movable object on every demo slide, plus a hero equation with three
definitions (the layout where the PI first met the defect), is resized from
two handles and then moved with real pointer input. After each gesture every
other object on the slide must paint exactly where it painted before."""
import json
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

HERO = 'independent-hero'
BOXES = """sid => Object.fromEntries([...document.querySelectorAll(
    `.slide-canvas[data-slide-id="${sid}"] [data-transform-target]`)]
  .filter(e => !e.closest('.curator-deleted'))
  .map(e => {const c = e.closest('.slide-canvas').getBoundingClientRect(), r = e.getBoundingClientRect(), s = c.width / 1920;
    return [e.dataset.transformTarget, [r.left - c.left, r.top - c.top, r.width, r.height].map(v => Math.round(v / s * 10) / 10)];}))"""


def hero_slide(after):
    spec = make_starter('hero-equation', HERO, '2030-01-01T00:00:00Z', after)
    text = spec['components']
    spec['data']['definitions'] = []
    # Long definitions wrap, so the row shrinks and stretches them to share it.
    for index, words in enumerate(('κ — fixed cost: examples one skill needs once its prerequisites are learned',
                                   'T — share of the data at depth i or deeper: uniform order\'s rate',
                                   'F — share shallower than k: where the curriculum\'s block starts')):
        key = f'definition-{index}'
        text[key] = {'kind': 'text', 'text': words}
        spec['data']['definitions'].append(key)
    del text['definition']
    return spec


def main():
    with tempfile.TemporaryDirectory(prefix='slide-independent-') as temp:
        root = Path(temp)
        shutil.copytree(ROOT / 'slides', root / 'slides')
        last = sorted(json.loads(p.read_text())['id'] for p in (root / 'slides').glob('*.json'))[-1]
        (root / 'slides' / f'{HERO}.json').write_text(json.dumps(hero_slide(last)))
        state_path = root / 'state.json'
        http = make_server(ROOT / 'public', root / 'slides', ROOT / 'data/seed-state.json', state_path)
        threading.Thread(target=http.serve_forever, daemon=True).start()
        failures, gestures = [], 0
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={'width': 1600, 'height': 1000})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                base = f'http://127.0.0.1:{http.server_address[1]}/'
                page.goto(base + '#' + HERO, wait_until='networkidle')
                page.locator('[data-edit-toggle]').click()
                slides = page.evaluate("[...document.querySelectorAll('.thumb[data-id]')].map(t => t.dataset.id)")

                def saved():
                    page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'", timeout=15000)
                    page.wait_for_timeout(120)

                def drag(x, y, dx, dy):
                    page.mouse.move(x, y); page.keyboard.down('Alt'); page.mouse.down()
                    page.mouse.move(x + dx, y + dy, steps=6); page.mouse.up(); page.keyboard.up('Alt')

                def check(sid, gesture, before):
                    nonlocal gestures
                    gestures += 1
                    saved()
                    frame = page.locator('.transform-frame')
                    selected = set(frame.get_attribute('data-transform-frame').split('|')) if frame.count() else set()
                    after = page.evaluate(BOXES, sid)
                    # A quarter canonical pixel: sub-pixel layout noise, far below what anyone sees.
                    moved = {key: (before[key], after.get(key)) for key in before if key not in selected
                             and (after.get(key) is None or max(abs(a - b) for a, b in zip(after[key], before[key])) > .25)}
                    if moved:
                        failures.append({'slide': sid, 'gesture': gesture, 'moved': moved})

                for sid in slides:
                    page.evaluate('id => { location.hash = id; }', sid)
                    page.locator(f'.slide-canvas[data-slide-id="{sid}"]').wait_for()
                    page.wait_for_timeout(300)
                    for key in page.evaluate(BOXES, sid):
                        target = page.locator(f'.slide-canvas[data-slide-id="{sid}"] [data-transform-target="{key}"]').first
                        r = target.bounding_box()
                        if not r or r['width'] < 12 or r['height'] < 12:
                            continue
                        page.keyboard.press('Escape'); page.keyboard.press('Escape')
                        # A border press selects without entering text editing.
                        page.mouse.click(r['x'] + 2, r['y'] + r['height'] / 2)
                        if not page.locator('.transform-frame').count():
                            continue
                        for handle, dx, dy in (('e', 70, 0), ('s', 0, 45)):
                            control = page.locator(f'.transform-frame [data-handle="{handle}"]')
                            if not control.count():
                                continue
                            before = page.evaluate(BOXES, sid)
                            c = control.bounding_box()
                            drag(c['x'] + c['width'] / 2, c['y'] + c['height'] / 2, dx, dy)
                            check(sid, f'resize {key} {handle}', before)
                        grip = page.locator('.transform-frame .transform-move-grip')
                        before = page.evaluate(BOXES, sid)
                        if grip.count():
                            g = grip.first.bounding_box()
                            drag(g['x'] + g['width'] / 2, g['y'] + g['height'] / 2, 40, 30)
                        else:
                            box = target.bounding_box()
                            drag(box['x'] + 3, box['y'] + box['height'] / 2, 40, 30)
                        check(sid, f'move {key}', before)
                browser.close()
        finally:
            http.shutdown(); http.server_close()
    assert not errors, errors
    assert gestures > 20, f'only {gestures} gestures ran'
    assert not failures, json.dumps(failures[:6], indent=1)
    print(json.dumps({'ok': True, 'slides': len(slides), 'gestures': gestures}))


if __name__ == '__main__':
    main()

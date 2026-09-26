#!/usr/bin/env python3
# browser-check: scratch
"""Seeded random real-input editing across several objects.

Every new gesture joins OPERATIONS. After each step the saved geometry must
match what the editor paints and no other slide may change; undoing
everything must restore the exact starting state; a reload must paint exactly
what was saved. Failures print the seed and the operation trace.
"""
import argparse
import json
from pathlib import Path
import random
import shutil
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server import make_server
from playwright.sync_api import sync_playwright

SLIDE = 'mock-angle-evidence'
HANDLES = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w']
NAMES = {'nw': 'top-left', 'n': 'top', 'ne': 'top-right', 'e': 'right', 's': 'bottom',
         'sw': 'bottom-left', 'w': 'left'}


class Session:
    def __init__(self, page, state_path, rng, trace):
        self.page, self.state_path, self.rng, self.trace = page, state_path, rng, trace

    def saved(self):
        self.page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'", timeout=15000)
        return json.loads(self.state_path.read_text())

    def targets(self):
        return self.page.evaluate("""()=>[...document.querySelectorAll('[data-stage] [data-transform-target]')]
          .filter(e=>e.getBoundingClientRect().width>8 && !e.closest('.curator-deleted'))
          .map(e=>e.dataset.transformTarget).filter((k,i,a)=>a.indexOf(k)===i)""")

    def element(self, key):
        return self.page.locator(f'[data-stage] [data-transform-target="{key}"]').first

    def center(self, key):
        r = self.element(key).bounding_box()
        return r['x'] + r['width'] * self.rng.uniform(.25, .75), r['y'] + r['height'] * self.rng.uniform(.3, .7)

    def drag(self, x, y, dx, dy, shift=False):
        page = self.page
        page.mouse.move(x, y)
        if shift: page.keyboard.down('Shift')
        page.mouse.down(); page.mouse.move(x + dx, y + dy, steps=5); page.mouse.up()
        if shift: page.keyboard.up('Shift')

    # --- operations: each is one real user action --------------------------
    def select(self):
        key = self.rng.choice(self.targets()); x, y = self.center(key)
        self.page.mouse.click(x, y); return 'select ' + key

    def move(self):
        key = self.rng.choice(self.targets()); x, y = self.center(key)
        self.page.keyboard.press('Escape'); self.page.keyboard.press('Escape')
        dx, dy = self.rng.randint(-120, 120), self.rng.randint(-80, 80)
        self.drag(x, y, dx, dy); return f'move {key} {dx},{dy}'

    def resize(self):
        if not self.page.locator('.transform-frame').count(): return self.select()
        handle = self.rng.choice(HANDLES)
        control = self.page.locator('.transform-frame ' + (f'[data-handle="{handle}"]'))
        if not control.count(): return 'resize-skipped'
        r = control.bounding_box()
        dx, dy = self.rng.randint(-60, 60), self.rng.randint(-40, 40)
        shift = self.rng.random() < .25
        self.drag(r['x'] + r['width'] / 2, r['y'] + r['height'] / 2, dx, dy, shift)
        return f'resize {handle} {dx},{dy} shift={shift}'

    def nudge(self):
        if not self.page.locator('.transform-frame').count(): return self.select()
        if self.page.evaluate('document.activeElement.isContentEditable'): self.page.keyboard.press('Escape')
        key = self.rng.choice(['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'])
        shift = self.rng.random() < .5
        for _ in range(self.rng.randint(1, 4)): self.page.keyboard.press(('Shift+' if shift else '') + key)
        return f'nudge {key} shift={shift}'

    def type(self):
        texts = [k for k in self.targets() if 'object:' not in k]
        key = self.rng.choice(texts); x, y = self.center(key)
        self.page.mouse.click(x, y)
        if not self.page.evaluate('document.activeElement.isContentEditable'): return 'type-skipped ' + key
        word = self.rng.choice(['alpha', 'β-test', ' 42', 'Z'])
        self.page.keyboard.type(word); return f'type {key} {word!r}'

    def undo(self):
        self.page.keyboard.press('Escape'); self.page.keyboard.press('Escape')
        self.page.keyboard.press('ControlOrMeta+z'); return 'undo'

    def escape(self):
        self.page.keyboard.press('Escape'); return 'escape'

    OPERATIONS = {'select': 2, 'move': 4, 'resize': 4, 'nudge': 3, 'type': 2, 'undo': 2, 'escape': 1}

    def step(self):
        names = list(self.OPERATIONS)
        name = self.rng.choices(names, [self.OPERATIONS[n] for n in names])[0]
        return getattr(self, name)()

    # --- invariants ---------------------------------------------------------
    def check(self, state, initial):
        page = self.page
        errors = []
        others = {k: v for k, v in state['overlays'].items() if k != SLIDE}
        if others != {k: v for k, v in initial['overlays'].items() if k != SLIDE}:
            errors.append('another slide changed')
        if page.locator('.transform-frame').count() > 1: errors.append('more than one frame')
        # Saved region sizes are what the editor paints.
        painted = page.evaluate("""sid=>Object.fromEntries([...document.querySelectorAll('[data-stage] [data-text-region-for]')]
          .map(e=>{const c=e.closest('.slide-canvas').getBoundingClientRect(),r=e.getBoundingClientRect(),s=c.width/1920;
            return [e.dataset.textRegionFor,{width:r.width/s,height:r.height/s}]}))""", SLIDE)
        regions = {}
        for cid, overlay in state['overlays'].get(SLIDE, {}).items():
            if 'region' in overlay: regions[cid] = overlay['region']
        for cid, box in state.get('textBoxes', {}).get(SLIDE, {}).items():
            if 'region' in box and not box.get('deleted'): regions[cid] = box['region']
        for cid, region in regions.items():
            if cid in painted and (abs(painted[cid]['width'] - region['width']) > 1.5 or abs(painted[cid]['height'] - region['height']) > 1.5):
                errors.append(f'{cid} painted {painted[cid]} but saved {region}')
        return errors


def run(seed, steps, reload_phase):
    rng = random.Random(seed)
    trace = []
    with tempfile.TemporaryDirectory(prefix='slide-fuzz-') as temp:
        root = Path(temp); shutil.copytree(ROOT/'slides', root/'slides')
        state_path = root/'state.json'
        http = make_server(ROOT/'public', root/'slides', ROOT/'data/seed-state.json', state_path)
        threading.Thread(target=http.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={'width': 1500, 'height': 950})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('console', lambda message: message.type == 'error' and errors.append(message.text))
                page.goto(f'http://127.0.0.1:{http.server_address[1]}/#{SLIDE}', wait_until='networkidle')
                # Every editor message is evidence (conflicts, refused undos).
                page.evaluate('''()=>{window.__toasts=[];const t=document.querySelector('[data-toast]');
                  new MutationObserver(()=>window.__toasts.push(t.textContent)).observe(t,{childList:true,characterData:true,subtree:true});}''')
                page.locator(f'.slide-canvas[data-slide-id="{SLIDE}"]').wait_for()
                page.locator('[data-edit-toggle]').click()
                session = Session(page, state_path, rng, trace)
                pristine = json.loads(state_path.read_text()) if state_path.exists() else None
                # A human text box joins the population of movable objects; undo
                # all must remove it too, returning to the pristine deck.
                page.locator('[data-add-text]').click(); page.keyboard.type('Fuzz note'); page.keyboard.press('Escape')
                initial = session.saved()
                pristine = pristine or {**initial, 'textBoxes': {}}
                for _ in range(steps):
                    trace.append(session.step())
                    problems = session.check(session.saved(), initial) + errors
                    if problems: raise AssertionError({'seed': seed, 'problems': problems, 'trace': trace, 'messages': page.evaluate('window.__toasts')})
                if reload_phase:
                    final = session.saved()
                    page.reload(wait_until='networkidle'); page.locator('.slide-canvas').wait_for(); page.wait_for_timeout(400)
                    problems = session.check(final, initial)
                    if problems: raise AssertionError({'seed': seed, 'reload': problems, 'trace': trace, 'messages': page.evaluate('window.__toasts')})
                else:
                    page.keyboard.press('Escape'); page.keyboard.press('Escape')
                    for _ in range(400):
                        if page.locator('[data-undo]').is_disabled(): break
                        page.keyboard.press('ControlOrMeta+z'); session.saved()
                    final = session.saved()
                    for field in ('overlays', 'objects', 'tables', 'textBoxes', 'order', 'hidden'):
                        if (final.get(field) or {}) != (pristine.get(field) or {}):
                            raise AssertionError({'seed': seed, 'undo-all differs': field,
                                                  'pristine': pristine.get(field), 'final': final.get(field), 'trace': trace, 'messages': page.evaluate('window.__toasts')})
                if errors: raise AssertionError({'seed': seed, 'errors': errors, 'trace': trace, 'messages': page.evaluate('window.__toasts')})
                browser.close()
        finally:
            http.shutdown()
    return trace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds', type=int, nargs='*', default=[11, 29])
    parser.add_argument('--steps', type=int, default=40)
    args = parser.parse_args()
    summary = []
    for seed in args.seeds:
        for reload_phase in (False, True):
            trace = run(seed, args.steps, reload_phase)
            summary.append({'seed': seed, 'phase': 'reload' if reload_phase else 'undo-all', 'steps': len(trace),
                            'operations': sorted({t.split()[0] for t in trace})})
    print(json.dumps({'ok': True, 'runs': summary}))


if __name__ == '__main__':
    main()

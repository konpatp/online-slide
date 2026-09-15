#!/usr/bin/env python3
# browser-check: scratch
"""Real sidebar drags, delayed ACKs, hidden slides, cancellation and reload."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server import make_server
from playwright.sync_api import sync_playwright


def main():
    with tempfile.TemporaryDirectory(prefix='slide-sidebar-order-') as temp:
        root = Path(temp)
        shutil.copytree(ROOT/'slides', root/'slides')
        http = make_server(ROOT/'public', root/'slides', ROOT/'data/seed-state.json', root/'state.json')
        threading.Thread(target=http.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={'width':1920,'height':1080})
                errors, held = [], []
                page.on('pageerror', lambda error: errors.append(str(error)))
                url = f'http://127.0.0.1:{http.server_address[1]}/'
                page.goto(url, wait_until='networkidle')
                page.wait_for_selector('.thumb')
                def order():
                    return page.locator('[data-thumb-list] > .thumb').evaluate_all('(nodes)=>nodes.map(n=>n.dataset.id)')
                initial = order()
                active = page.locator('.slide-canvas').get_attribute('data-slide-id')
                page.locator('.slide-canvas').evaluate('el=>window.originalCanvas=el')
                page.locator(f'.thumb[data-id="{initial[1]}"] [data-action="visibility"]').click()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                before = json.loads((root/'state.json').read_text())
                page.locator('.slide-canvas').evaluate('el=>window.originalCanvas=el')
                page.route('**/api/deck-state*', lambda route: held.append(route)
                           if route.request.method=='POST' else route.continue_())
                def wait_writes(count):
                    end = time.monotonic()+5
                    while len(held)<count and time.monotonic()<end:
                        page.wait_for_timeout(30)
                    assert len(held)==count, (len(held),count)
                def drag(source, target, after=True, cancel=False):
                    card = page.locator(f'.thumb[data-id="{source}"]')
                    destination = page.locator(f'.thumb[data-id="{target}"]')
                    card.scroll_into_view_if_needed()
                    a=card.bounding_box(); b=destination.bounding_box()
                    page.mouse.move(a['x']+65,a['y']+35)
                    page.mouse.down()
                    page.mouse.move(a['x']+75,a['y']+45,steps=3)
                    page.wait_for_timeout(80)
                    assert page.locator('.thumb-drag-copy .thumb-title').is_visible()
                    assert page.locator('.thumb-drag-copy iframe').count()==0
                    page.mouse.move(b['x']+70,b['y']+b['height']*(.8 if after else .2),steps=15)
                    page.wait_for_timeout(200)
                    if cancel: page.keyboard.press('Escape')
                    page.mouse.up()
                    page.wait_for_timeout(220)
                drag(initial[0],initial[2])
                wait_writes(1)
                assert order()[:3]==[initial[1],initial[2],initial[0]], order()
                assert page.locator('.slide-canvas').evaluate('el=>el===window.originalCanvas')
                assert page.locator('.slide-canvas').get_attribute('data-slide-id')==active
                # A second drag remains responsive while first save is held.
                drag(initial[1],initial[0])
                assert order()[:3]==[initial[2],initial[0],initial[1]], order()
                assert len(held)==1
                held[0].fulfill(response=held[0].fetch())
                wait_writes(2)
                held[1].fulfill(response=held[1].fetch())
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                expected=order()
                page.unroute('**/api/deck-state*')
                saved=json.loads((root/'state.json').read_text())
                assert saved['order']==expected
                for field in ('hidden','overlays','tables','objects','textBoxes'):
                    assert saved.get(field)==before.get(field), field
                revision=saved['revision']
                drag(expected[0],expected[2],cancel=True)
                assert order()==expected
                assert json.loads((root/'state.json').read_text())['revision']==revision
                page.reload(wait_until='networkidle')
                assert order()==expected
                # Normal clicking still opens one slide; buttons remain usable.
                page.locator(f'.thumb[data-id="{expected[1]}"] .thumb-art').click()
                page.wait_for_function('id=>document.querySelector(".slide-canvas").dataset.slideId===id',arg=expected[1])
                page.locator(f'.thumb[data-id="{expected[1]}"] [data-action="move"][data-delta="-1"]').click()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                assert order()[0]==expected[1]
                # Upward drag uses the same permanent-ID move, not stale indices.
                drag(expected[1], expected[2])
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                drag(expected[1], expected[0], after=False)
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                assert order()[0]==expected[1]
                # Edge scrolling is owned by Sortable, even in a long rail.
                rail=page.locator('.filmstrip')
                rail.evaluate("el=>{el.style.height='430px';el.scrollTop=0}")
                card=page.locator('[data-thumb-list] > .thumb').first.bounding_box()
                bounds=rail.bounding_box()
                page.mouse.move(card['x']+65,card['y']+35); page.mouse.down()
                page.mouse.move(card['x']+80,card['y']+45,steps=3)
                page.wait_for_timeout(80)
                page.mouse.move(bounds['x']+80,bounds['y']+bounds['height']-12,steps=12)
                page.wait_for_function("document.querySelector('.filmstrip').scrollTop>40")
                page.keyboard.press('Escape'); page.mouse.up(); page.wait_for_timeout(220)
                rail.evaluate("el=>el.style.height=''")
                assert not errors, errors
                # Physical touch long-press uses the same saved identity path.
                touch=browser.new_page(viewport={'width':1920,'height':1080},has_touch=True)
                touch.on('pageerror', lambda error: errors.append(str(error)))
                touch.goto(url,wait_until='networkidle')
                touch_order=touch.locator('[data-thumb-list] > .thumb').evaluate_all('(ns)=>ns.map(n=>n.dataset.id)')
                a=touch.locator('[data-thumb-list] > .thumb').nth(0).bounding_box()
                b=touch.locator('[data-thumb-list] > .thumb').nth(2).bounding_box()
                cdp=touch.context.new_cdp_session(touch)
                def touch_event(kind,x=None,y=None):
                    cdp.send('Input.dispatchTouchEvent',{'type':kind,'touchPoints':[] if x is None else [{'x':x,'y':y}]})
                touch_event('touchStart',a['x']+65,a['y']+35)
                touch.wait_for_timeout(220)
                touch_event('touchMove',a['x']+80,a['y']+45)
                touch.wait_for_timeout(100)
                touch_event('touchMove',b['x']+80,b['y']+b['height']*.8)
                touch.wait_for_timeout(250)
                touch_event('touchEnd')
                touch.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                assert json.loads((root/'state.json').read_text())['order'][:3]==[touch_order[1],touch_order[2],touch_order[0]]
                assert not errors, errors
                browser.close()
        finally:
            http.shutdown(); http.server_close()
    print(json.dumps({'ok':True,'physicalDrags':True,'rapidDelayedSaves':True,
                      'hiddenAndContentPreserved':True,'cancelNoWrite':True,
                      'reloadPersistence':True,'navigationAndButtons':True,
                      'edgeScroll':True,'touchLongPress':True}))


if __name__=='__main__': main()

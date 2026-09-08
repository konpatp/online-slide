#!/usr/bin/env python3
"""Physical table formatting, edit/present equivalence, lazy rail and focus proof."""
import json
from pathlib import Path
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import server
from playwright.sync_api import sync_playwright


def main():
    with tempfile.TemporaryDirectory(prefix='slide-wysiwyg-') as temp:
        state_path = Path(temp)/'state.json'
        http = server.make_server(ROOT/'public',ROOT/'slides',ROOT/'data/seed-state.json',state_path)
        thread = threading.Thread(target=http.serve_forever,daemon=True); thread.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={'width':1920,'height':1080})
                errors, posts = [], []
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.on('request',lambda request: posts.append(request.url) if request.method=='POST' else None)
                base = 'http://127.0.0.1:%d/' % http.server_address[1]
                sid = 'mock-angle-evidence'
                page.goto(base+'#'+sid)
                table = page.locator('[data-stage] .evidence-table')
                table.wait_for(); page.wait_for_timeout(350)
                measure = '''table => ({scale:table.dataset.fitScale,
                    rows:[...table.rows].map(r=>r.getBoundingClientRect().height),
                    fonts:[...table.querySelectorAll('.semantic-component')].map(e=>getComputedStyle(e).fontSize)})'''
                normal = table.evaluate(measure)
                page.locator('[data-edit-toggle]').click(); page.wait_for_timeout(350)
                assert table.evaluate(measure) == normal, (normal,table.evaluate(measure))
                cell = page.locator('[data-stage] [data-component-id="random-mid"]')
                sibling = page.locator('[data-stage] [data-component-id="random-high"]')
                original_sibling = sibling.text_content()
                cell.click(); cell.fill('Plain bold tail')
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                cell.click(); page.keyboard.press('Home')
                for _ in range(6): page.keyboard.press('ArrowRight')
                for _ in range(4): page.keyboard.press('Shift+ArrowRight')
                assert page.evaluate('getSelection().toString()') == 'bold'
                page.locator('[data-bold]').click()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                saved = json.loads(state_path.read_text())
                assert saved['overlays'][sid]['random-mid']['marks'] == [{'start':6,'end':10,'bold':True}]
                page.reload(); cell.wait_for()
                assert cell.locator('[data-text-bold="true"]').text_content() == 'bold'
                assert sibling.text_content() == original_sibling
                assert cell.locator('[data-text-bold="true"]').evaluate('e=>getComputedStyle(e).fontWeight') == '700'
                # Real previews consume local state, not a second stale server copy.
                art = page.locator('.thumb[data-id="'+sid+'"] .thumb-art')
                page.wait_for_function('id=>document.querySelector(`.thumb[data-id="${id}"] .preview-ready`)',arg=sid)
                frame = art.locator('iframe').element_handle().content_frame()
                assert frame.locator('[data-component-id="random-mid"] [data-text-bold="true"]').text_content() == 'bold'
                assert not frame.locator('iframe').count()
                assert not frame.locator('.presentation-exit').is_visible()
                assert not any('/api/' in url for url in frame.evaluate('performance.getEntriesByType("resource").map(r=>r.name)'))
                assert page.locator('iframe').count() < 6
                writes = len(posts)
                page.wait_for_timeout(500); assert len(posts)==writes
                page.locator('[data-edit-toggle]').click()
                cell.click(); page.keyboard.press('Control+a'); page.keyboard.press('Control+b')
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                assert json.loads(state_path.read_text())['overlays'][sid]['random-mid']['marks'] == [
                    {'start':0,'end':15,'bold':True}]
                # Reload on the last slide follows focus; save/re-render respects
                # deliberate manual rail scrolling rather than snapping back.
                last = 'mock-target-accessibility'
                page.goto(base+'#'+last)
                page.locator('.slide-canvas[data-slide-id="'+last+'"]').wait_for()
                def in_rail():
                    return page.evaluate('''() => {const r=document.querySelector('.filmstrip').getBoundingClientRect();
                        const c=document.querySelector('.thumb.current').getBoundingClientRect();
                        return c.top>=r.top && c.bottom<=r.bottom;}''')
                assert in_rail()
                page.reload(); page.locator('.slide-canvas').wait_for(); assert in_rail()
                page.evaluate("document.querySelector('.filmstrip').scrollTop=0")
                page.locator('[data-edit-toggle]').click()
                assert page.locator('.filmstrip').evaluate('e=>e.scrollTop')==0
                page.locator('.thumb[data-id="mock-growth-trajectories"] .thumb-art').click()
                page.locator('.slide-canvas[data-slide-id="mock-growth-trajectories"]').wait_for()
                assert in_rail()
                assert not errors,errors
                browser.close()
                print(json.dumps({'ok':True,'editPresentGeometry':normal,'substringBoldDurable':True,
                    'realReadOnlyPreviews':True,'boundedLazyLoading':True,'refreshFollowsFocus':True,
                    'manualRailScrollPreserved':True,'liveWrites':0}))
        finally:
            http.shutdown(); http.server_close(); thread.join()


if __name__ == '__main__': main()

#!/usr/bin/env python3
# browser-check: scratch
"""Physical whole-object deletion and multi-action undo; never touches live state."""
import json
from pathlib import Path
import sys
import tempfile
import threading
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server import make_server
from playwright.sync_api import sync_playwright

def main():
    with tempfile.TemporaryDirectory(prefix='slide-delete-undo-') as temp:
        state_path=Path(temp)/'state.json'
        http=make_server(ROOT/'public',ROOT/'slides',ROOT/'data/seed-state.json',state_path)
        threading.Thread(target=http.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch();page=browser.new_page(viewport={'width':1920,'height':1080})
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                url='http://127.0.0.1:%d/'%http.server_address[1]
                def saved():
                    page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                def undo():
                    page.locator('[data-undo]').click();saved()
                    page.wait_for_timeout(100)
                def data(): return json.loads(state_path.read_text())
                page.goto(url+'#mock-angle-evidence')
                page.locator('.slide-canvas').wait_for()
                if page.locator('[data-edit-toggle]').inner_text()=='Enable edit': page.locator('[data-edit-toggle]').click()
                title=page.locator('[data-stage] .slide-title')
                original=title.inner_text()
                # Backspace while typing edits characters, not the whole object.
                title.fill('Undo this text');page.keyboard.press('Backspace');saved()
                assert title.inner_text()=='Undo this tex'
                assert not title.evaluate("e=>e.classList.contains('curator-deleted')")
                page.keyboard.press('Control+z');saved()
                page.wait_for_function('s=>document.querySelector("[data-stage] .slide-title").textContent===s',arg=original)
                # Four distinct actions, with a successful server ACK after each.
                page.locator('[data-add-text]').click();saved()
                box=page.locator('[data-stage] [data-component-id^="text-box-"]')
                box.wait_for();key=box.get_attribute('data-component-id')
                box.fill('Keep this annotation');saved()
                before_move=data()['textBoxes']['mock-angle-evidence'][key]['region']
                move=page.get_by_role('button',name='Move text region',exact=True)
                a=move.bounding_box();page.mouse.move(a['x']+15,a['y']+4);page.mouse.down()
                page.mouse.move(a['x']+70,a['y']+44,steps=8);page.mouse.up();saved()
                moved=data()['textBoxes']['mock-angle-evidence'][key]['region']
                assert moved!=before_move
                # Handle selection owns the whole object, so Backspace deletes it.
                page.keyboard.press('Backspace');saved();assert not box.is_visible()
                assert data()['textBoxes']['mock-angle-evidence'][key]['deleted']
                undo();assert box.is_visible();assert box.inner_text()=='Keep this annotation'
                assert data()['textBoxes']['mock-angle-evidence'][key]['region']==moved
                undo();assert data()['textBoxes']['mock-angle-evidence'][key]['region']==before_move
                undo();assert box.inner_text()=='Type your text'
                undo();assert box.count()==0
                assert page.locator('.slide-canvas').get_attribute('data-slide-id')=='mock-angle-evidence'
                # Authored deletion persists on reload; source is not erased.
                title.click();page.keyboard.press('Escape');page.keyboard.press('Delete');saved()
                assert not title.is_visible()
                page.reload();page.locator('.slide-canvas').wait_for();assert not title.is_visible()
                # A node deletion includes its connectors, without changing siblings.
                page.goto(url+'#mock-vector-construction')
                if page.locator('[data-edit-toggle]').inner_text()=='Enable edit': page.locator('[data-edit-toggle]').click()
                node=page.locator('.joint-element[model-id="teacher-node"]')
                node.wait_for();a=node.bounding_box()
                page.mouse.click(a['x']+5,a['y']+5)
                page.wait_for_function("document.querySelector('[data-selected-component]').textContent.includes('teacher-node')")
                page.keyboard.press('Delete');saved()
                assert not node.is_visible()
                assert not page.locator('[data-diagram-node-id="teacher-node"]').is_visible()
                assert not page.locator('.joint-link[model-id="query-to-teacher"]').is_visible()
                assert page.locator('.joint-element[model-id="student-node"]').is_visible()
                undo();node.wait_for();assert page.locator('.joint-link[model-id="query-to-teacher"]').is_visible()
                # Delete an image independently and undo it after acknowledgement.
                page.goto(url+'#mock-matched-gallery');page.locator('.gallery-cell').first.wait_for()
                if page.locator('[data-edit-toggle]').inner_text()=='Enable edit': page.locator('[data-edit-toggle]').click()
                image=page.locator('[data-stage] .gallery-cell').first
                image.click(position={'x':25,'y':25});page.keyboard.press('Delete');saved();assert not image.is_visible()
                undo();assert image.is_visible()
                page.goto(url+'#mock-guidance-vector-geometry')
                if page.locator('[data-edit-toggle]').inner_text()=='Enable edit': page.locator('[data-edit-toggle]').click()
                page.wait_for_function("document.querySelector('.jsxgraph-host')?.__scientificGeometry?.controls.has('raw')")
                point=page.locator('.jsxgraph-host').evaluate("""el=>{
                  const c=el.__scientificGeometry.controls.get('raw'),r=el.getBoundingClientRect();
                  const a=c.start.coords.scrCoords,b=c.end.coords.scrCoords;
                  return {x:r.x+(a[1]*.3+b[1]*.7)*r.width/el.clientWidth,
                          y:r.y+(a[2]*.3+b[2]*.7)*r.height/el.clientHeight};
                }""")
                page.mouse.click(point['x'],point['y'])
                page.wait_for_function("document.querySelector('[data-selected-component]').textContent.includes('raw')")
                page.keyboard.press('Backspace');saved()
                assert data().get('objects',{}).get('mock-guidance-vector-geometry',{}).get('raw',{}).get('deleted'), page.evaluate("({active:document.activeElement.outerHTML.slice(0,800), selected:document.querySelector('[data-selected-component]').textContent, status:document.querySelector('[data-save-state]').textContent})")
                page.wait_for_function("!document.querySelector('.jsxgraph-host').__scientificGeometry.controls.has('raw')")
                undo()
                page.wait_for_function("document.querySelector('.jsxgraph-host').__scientificGeometry.controls.has('raw')")
                assert not errors,errors
                browser.close()
        finally:http.shutdown();http.server_close()
    print('PASS text/whole-object distinction; saved multi-step undo of typing, movement and deletion; deletion reload; node/connector/image deletion; unrelated content preserved')

if __name__=='__main__':main()

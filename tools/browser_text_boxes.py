#!/usr/bin/env python3
# browser-check: scratch
"""Real pointer insertion, typing, formatting, resize and reload; scratch only."""
import json, sys, tempfile, threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import server
from playwright.sync_api import sync_playwright

def main():
    with tempfile.TemporaryDirectory(prefix='slide-text-box-') as temp:
        state_path=Path(temp)/'state.json'
        http=server.make_server(ROOT/'public',ROOT/'slides',ROOT/'data/seed-state.json',state_path)
        threading.Thread(target=http.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch();page=browser.new_page(viewport={'width':1920,'height':1080})
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto('http://127.0.0.1:%d/#mock-angle-evidence'%http.server_address[1])
                page.locator('[data-stage] .evidence-table').wait_for()
                page.locator('[data-edit-toggle]').click()
                page.locator('[data-add-text]').click()
                box=page.locator('[data-stage] [data-component-id^="text-box-"]')
                box.wait_for();page.wait_for_function("document.activeElement.matches('[data-component-id^=\"text-box-\"]')")
                page.keyboard.type('A readable note that wraps inside its own padded text region.')
                page.keyboard.press('Enter');page.keyboard.type('Second line')
                page.keyboard.press('Shift+Enter');page.keyboard.type('Third line')
                page.locator('[data-bold]').click()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                saved=json.loads(state_path.read_text());sid='mock-angle-evidence'
                key=next(iter(saved['textBoxes'][sid]))
                assert saved['textBoxes'][sid][key]['text'].startswith('A readable note')
                assert saved['textBoxes'][sid][key]['text'].endswith('\nSecond line\nThird line'), (saved['textBoxes'][sid][key],box.inner_html())
                assert saved['textBoxes'][sid][key]['marks']
                # Both canonical-coordinate region handles remain available.
                resize=page.get_by_role('button',name='Resize text region',exact=True)
                rect=resize.bounding_box();assert rect
                page.mouse.move(rect['x']+rect['width']/2,rect['y']+rect['height']/2)
                page.mouse.down();page.mouse.move(rect['x']+70,rect['y']+40,steps=5);page.mouse.up()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                after=json.loads(state_path.read_text())
                assert after['textBoxes'][sid][key]['region']!=saved['textBoxes'][sid][key]['region']
                box.click()
                move=page.get_by_role('button',name='Move text region',exact=True)
                rect=move.bounding_box();assert rect
                page.mouse.move(rect['x']+20,rect['y']+4);page.mouse.down()
                page.mouse.move(rect['x']+70,rect['y']+24,steps=5);page.mouse.up()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                moved=json.loads(state_path.read_text())
                assert moved['textBoxes'][sid][key]['region']['x']!=after['textBoxes'][sid][key]['region']['x']
                after=moved
                page.reload();box.wait_for()
                assert box.locator('[data-text-bold=true]').count()
                assert json.loads(state_path.read_text())['textBoxes']==after['textBoxes']
                page.locator('[data-edit-toggle]').click();page.wait_for_timeout(350)
                canvas=page.locator('[data-stage] .slide-canvas');bounds=canvas.bounding_box()
                # Empty bottom-left margin, away from content and controls.
                page.mouse.dblclick(bounds['x']+20,bounds['y']+bounds['height']-25)
                page.wait_for_function("document.querySelectorAll('[data-stage] [data-component-id^=\"text-box-\"]').length===2")
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                page.locator('[data-stage] .slide-title').dblclick()
                assert box.count()==2,'double-clicking authored text must not insert'
                title=page.locator('[data-stage] .slide-title')
                title.fill('First title line');page.keyboard.press('Enter');page.keyboard.type('Second title line')
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                page.reload();title.wait_for()
                assert title.text_content()=='First title line\nSecond title line'
                assert title.evaluate('e=>getComputedStyle(e).whiteSpace')=='pre-wrap'
                assert not errors,errors
                page.screenshot(path='/tmp/text-box-editor-proof.png')
                browser.close()
        finally:http.shutdown();http.server_close()
    print('PASS button/double-click text insertion, typing, bold, resize and refresh persistence')

if __name__=='__main__':main()

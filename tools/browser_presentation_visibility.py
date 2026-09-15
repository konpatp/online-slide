#!/usr/bin/env python3
# browser-check: scratch
"""Audience mode never paints hidden slides; editor and previews retain access."""
import json
from pathlib import Path
import sys
import tempfile
import threading
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server import make_server
from slidekit import load_catalog,reconcile_state
from playwright.sync_api import sync_playwright

def main():
    with tempfile.TemporaryDirectory(prefix='slide-visibility-') as temp:
        root=Path(temp)
        seed,_=reconcile_state(json.loads((ROOT/'data/seed-state.json').read_text()),load_catalog(ROOT/'slides'))
        order=seed['order'];visible=[order[1],order[3]]
        seed['hidden']=[key for key in order if key not in visible]
        seed_path=root/'seed.json';seed_path.write_text(json.dumps(seed))
        http=make_server(ROOT/'public',ROOT/'slides',seed_path,root/'state.json')
        threading.Thread(target=http.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch();page=browser.new_page(viewport={'width':1920,'height':1080})
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                url=f'http://127.0.0.1:{http.server_address[1]}/'
                page.add_init_script("""window.hiddenPaints=[];new MutationObserver(()=>{
                  const c=document.querySelector('.slide-canvas');
                  if(c && document.body.classList.contains('present-only')) window.hiddenPaints.push(c.dataset.slideId);
                }).observe(document,{childList:true,subtree:true});""")
                def at(key):page.wait_for_function('id=>document.querySelector(".slide-canvas")?.dataset.slideId===id',arg=key)
                page.goto(url+'?present=1#'+order[0]);at(visible[0])
                assert page.locator('[data-position]').inner_text()=='1 / 2'
                page.keyboard.press('ArrowRight');at(visible[1])
                page.keyboard.press('ArrowRight');at(visible[1])
                page.keyboard.press('ArrowLeft');at(visible[0])
                page.evaluate('id=>location.hash=id',order[2]);at(visible[1])
                page.reload();at(visible[1])
                assert not set(page.evaluate('window.hiddenPaints'))-set(visible)
                page.keyboard.press('Escape')
                assert not page.locator('body').evaluate("e=>e.classList.contains('present-only')")
                page.evaluate('id=>location.hash=id',order[0]);at(order[0])
                assert page.locator('[data-thumb-list] > .thumb').count()==len(order)
                page.wait_for_function('id=>document.querySelector(`.thumb[data-id="${id}"] .preview-ready`)',arg=order[0])
                preview=page.locator(f'.thumb[data-id="{order[0]}"] iframe').element_handle().content_frame()
                assert preview.locator('.slide-canvas').get_attribute('data-slide-id')==order[0]
                page.locator('[data-fullscreen-toggle]').click();at(visible[0])
                assert page.locator('body').evaluate("e=>e.classList.contains('present-only')")
                page.keyboard.press('ArrowRight');at(visible[1])
                assert set(page.request.get(url+'api/deck-state').json()['hidden'])==set(seed['hidden'])
                page.keyboard.press('Escape')
                for key in visible:
                    page.locator(f'.thumb[data-id="{key}"] [data-action="visibility"]').click()
                    page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                page.locator('[data-fullscreen-toggle]').click()
                assert not page.locator('body').evaluate("e=>e.classList.contains('present-only')")
                page.goto(url+'?present=1#'+order[0]);at(order[0])
                assert not page.locator('body').evaluate("e=>e.classList.contains('present-only')")
                assert not errors,errors
                browser.close()
        finally:http.shutdown();http.server_close()
    print('PASS hidden first/middle/last slide, direct hash, reload, keyboard, fullscreen entry, all-hidden refusal and editor access')

if __name__=='__main__':main()

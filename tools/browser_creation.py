#!/usr/bin/env python3
"""Physical create/preview/type/save/reload + uncertain-ACK retry in scratch."""
import json
from pathlib import Path
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import server
from playwright.sync_api import sync_playwright


def main():
    with tempfile.TemporaryDirectory(prefix='slide-creation-') as temp:
        state_path = Path(temp)/'state.json'
        http = server.make_server(ROOT/'public', ROOT/'slides', ROOT/'data/seed-state.json', state_path)
        thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width': 1920, 'height': 1080})
                errors = []; page.on('pageerror', lambda error: errors.append(str(error)))
                base = 'http://127.0.0.1:%d/' % http.server_address[1]
                page.goto(base)
                page.locator('[data-new-slide]:enabled').wait_for()
                initial = json.loads(state_path.read_text())
                anchor = initial['order'][0]
                page.locator('[data-new-slide]').click()
                page.locator('[data-layout="section-divider"][aria-pressed="true"]').wait_for()
                frame = page.frame_locator('[data-layout-preview] iframe')
                frame.locator('.centered-section .slide-title').wait_for()
                page.keyboard.press('ArrowRight')
                assert page.locator('[data-stage] article').get_attribute('data-slide-id') == anchor
                assert state_path.read_text() == json.dumps(initial, indent=2, sort_keys=True)+'\n'
                page.screenshot(path='/tmp/new-slide-picker.png')
                page.locator('[data-create-confirm]').click()
                page.locator('[data-create-dialog]').wait_for(state='hidden')
                title = page.locator('[data-stage] [data-component-id="headline"]')
                page.wait_for_function("document.activeElement?.dataset.componentId === 'headline'")
                page.keyboard.type('A new chapter')
                page.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                created_id = page.url.split('#')[1]
                saved = json.loads(state_path.read_text())
                assert saved['order'][1] == created_id and saved['order'][0] == anchor
                assert saved['overlays'][created_id]['headline']['text'] == 'A new chapter'
                page.locator('[data-edit-toggle]').click()
                page.screenshot(path='/tmp/new-slide-section.png')
                center = title.evaluate('e=>{const r=e.getBoundingClientRect(),c=e.closest("article").getBoundingClientRect();return {text:getComputedStyle(e).textAlign,delta:Math.abs(r.y+r.height/2-c.y-c.height/2)}}')
                assert center['text'] == 'center' and center['delta'] < 25, center
                page.reload(); title.wait_for(); assert title.text_content() == 'A new chapter'
                # Cached old slide source must survive bootstrap ACK metadata.
                page.locator('.thumb[data-id="'+anchor+'"] .thumb-card').click()
                page.locator('[data-stage] [data-slide-id="'+anchor+'"]').wait_for()
                # Commit but deliberately lose its response, then reload and retry.
                calls = []
                def lose_ack(route):
                    calls.append(route.request.post_data_json)
                    route.fetch(); route.abort()
                page.route('**/api/slides*', lose_ack)
                page.locator('[data-new-slide]').click()
                page.locator('[data-layout="evidence-table"]').click()
                page.locator('[data-create-confirm]').click()
                page.get_by_text('No confirmed response.', exact=False).wait_for()
                page.reload(); page.locator('[data-new-slide]:enabled').wait_for()
                page.unroute('**/api/slides*', lose_ack)
                page.locator('[data-new-slide]').click()
                page.get_by_role('button', name='Retry creating slide').click()
                page.locator('[data-create-dialog]').wait_for(state='hidden')
                table_id = page.url.split('#')[1]
                page.locator('[data-stage] [data-component-id="first-first"]').fill('42')
                page.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                page.reload()
                assert page.locator('[data-stage] [data-component-id="first-first"]').text_content() == '42'
                final = json.loads(state_path.read_text())
                assert len(final['order']) == len(initial['order'])+2
                assert final['createdSlides'][table_id]['creation']['requestId'] == calls[0]['requestId']
                assert final['hidden'] == initial['hidden']
                assert not errors, errors
                # Every offered starter must render with the actual engine.
                page.locator('[data-new-slide]').click()
                for recipe in ('evidence-table', 'evidence-figure', 'mechanism-pipeline',
                               'hierarchical-gallery', 'hero-equation'):
                    page.locator('[data-layout="'+recipe+'"]').click()
                    preview_frame = page.frame_locator('[data-layout-preview] iframe')
                    preview_frame.locator('.recipe-'+recipe).wait_for()
                    if recipe == 'hero-equation':
                        preview_frame.locator('[data-math-engine="katex"]').first.wait_for()
                    elif recipe == 'mechanism-pipeline':
                        preview_frame.locator('.joint-element').first.wait_for()
                    page.wait_for_timeout(150)
                    page.screenshot(path='/tmp/new-slide-'+recipe+'.png')
                page.locator('[data-create-cancel]').click()
                page.locator('[data-layouts-link]').click()
                page.locator('#section-divider a').first.click()
                page.locator('[data-layout="section-divider"][aria-pressed="true"]').wait_for()
                assert page.url.split('#')[1] == table_id
                page.locator('[data-create-cancel]').click()
                assert not errors, errors
                print(json.dumps({'physicalCreate': True, 'titleSaved': True, 'tableCellSaved': True,
                                  'lostAckReloadRetry': True, 'duplicates': 0, 'pageErrors': errors}))
                browser.close()
        finally:
            http.shutdown(); http.server_close(); thread.join(timeout=2)


if __name__ == '__main__':
    main()

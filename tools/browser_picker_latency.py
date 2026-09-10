#!/usr/bin/env python3
# browser-check: scratch
"""Measure a distant layout picker and prove switching needs no page reload."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server import make_server
from playwright.sync_api import sync_playwright


def main():
    with tempfile.TemporaryDirectory(prefix='picker-latency-') as temp:
        state_path = Path(temp)/'state.json'
        http = make_server(ROOT/'public', ROOT/'slides', ROOT/'data/seed-state.json', state_path)
        thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={'width': 1920, 'height': 1080})
                errors = []; page.on('pageerror', lambda e: errors.append(str(e)))
                cdp = page.context.new_cdp_session(page); cdp.send('Network.enable')
                cdp.send('Network.emulateNetworkConditions', {'offline': False, 'latency': 350,
                         'downloadThroughput': 625000, 'uploadThroughput': 250000})
                page.goto('http://127.0.0.1:%d/#mock-angle-evidence' % http.server_address[1])
                before = state_path.read_bytes()
                timings = []
                def ready():
                    page.locator('[data-layout-preview][aria-busy="false"]').wait_for()
                start = time.perf_counter(); page.locator('[data-new-slide]:enabled').click(); ready()
                timings.append(['open', round((time.perf_counter()-start)*1000)])
                frame = page.locator('[data-layout-preview] iframe').element_handle()
                preview_page = frame.content_frame()
                preview_page.evaluate('window.pickerInstance = "retained"')
                requests = []
                page.on('request', lambda r: requests.append(r.url) if r.frame == preview_page else None)
                for recipe in ('evidence-table', 'section-divider', 'evidence-table', 'section-divider'):
                    start = time.perf_counter(); page.locator('[data-layout="'+recipe+'"]').click(); ready()
                    preview_page.locator('.recipe-'+recipe).wait_for()
                    timings.append([recipe, round((time.perf_counter()-start)*1000)])
                    assert preview_page.evaluate('window.pickerInstance') == 'retained'
                assert not requests, requests
                # Delayed optional diagram code cannot replace the latest choice.
                page.locator('[data-layout="mechanism-pipeline"]').click()
                page.locator('[data-layout="section-divider"]').click(); ready()
                page.wait_for_timeout(1200)
                assert preview_page.locator('.centered-section').count() == 1
                page.locator('[data-create-cancel]').click()
                start = time.perf_counter(); page.locator('[data-new-slide]').click(); ready()
                timings.append(['reopen', round((time.perf_counter()-start)*1000)])
                assert preview_page.evaluate('window.pickerInstance') == 'retained'
                assert len(page.locator('[data-layout-preview] iframe').all()) == 1
                page.screenshot(path='/tmp/layout-picker-fast.png')
                assert state_path.read_bytes() == before
                assert not errors, errors
                print(json.dumps({'latencyMs': 350, 'downloadMbps': 5, 'timingsMs': timings,
                                  'requestsWhileSwitchingSimpleLayouts': 0, 'retainedRenderer': True,
                                  'lateWorkFenced': True, 'stateUnchanged': True, 'errors': errors}))
                browser.close()
        finally:
            http.shutdown(); http.server_close(); thread.join(timeout=2)


if __name__ == '__main__': main()

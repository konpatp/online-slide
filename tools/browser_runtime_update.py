"""An open tab crosses a renderer release without mixed tables or lost edits."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import multiprocessing

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
import server
from test_table_panels import fixture
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    sources = args.output / 'slides'; sources.mkdir()
    spec = fixture()
    spec['components']['checkpoint'] = {'kind': 'text', 'text': 'Checkpoint'}
    spec['data']['tableSelector'] = {'label': 'checkpoint', 'options': [
        {'value': row['id'], 'label': row['heading']} for row in spec['data']['tables']]}
    (sources / 'tables.json').write_text(json.dumps(spec))
    old = args.output / 'old-public'; shutil.copytree(ROOT / 'public', old)
    path = old / 'recipes.js'
    # Simulate the pre-selector capability; versioning must prevent this renderer
    # from accepting a future release's source, even though both parse as tables.
    path.write_text(path.read_text().replace('var selector=slide.data.tableSelector;', 'var selector=null;'))
    state = args.output / 'state.json'
    def start(public, port=0):
        http = server.make_server(public, sources, ROOT / 'data/seed-state.json', state, port=port)
        bound = http.server_address[1]
        process = multiprocessing.Process(target=http.serve_forever, daemon=True); process.start()
        http.server_close()
        return process, bound
    def stop(pair):
        pair[0].terminate(); pair[0].join()
    running = start(old); port = running[1]
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={'width': 1920, 'height': 1080})
            base = f'http://127.0.0.1:{port}/'
            page.goto(base + '?present=1#two-tables', wait_until='networkidle')
            assert page.locator('[data-native-table]').count() == 2
            page.screenshot(path=str(args.output / 'before.png'))
            old_revision = page.evaluate('window.slidekitAssetRevision')
            stop(running); running = start(ROOT / 'public', port)
            page.evaluate("dispatchEvent(new Event('focus'))")
            page.wait_for_function('(old) => window.slidekitAssetRevision !== old', arg=old_revision)
            page.locator('.gallery-option-row button').first.wait_for()
            assert page.locator('[data-native-table]').count() == 1
            assert page.url.endswith('?present=1#two-tables')
            page.screenshot(path=str(args.output / 'after.png'))

            # A release during an unacknowledged edit must not reload or apply it.
            page.goto(base + '#two-tables', wait_until='networkidle')
            page.locator('[data-edit-toggle]').click()
            def offline(route):
                if route.request.method == 'POST': route.abort()
                else: route.continue_()
            page.route('**/api/deck-state*', offline)
            cell = page.locator('[data-component-id="primary-cell"]')
            cell.click(); cell.fill('Retain this unsaved edit')
            page.wait_for_function("document.querySelector('[data-save-state]').textContent.includes('Offline')")
            stored = state.read_bytes()
            latest = page.evaluate('window.slidekitAssetRevision')
            stop(running); running = start(old, port)
            page.evaluate("dispatchEvent(new Event('focus'))")
            page.wait_for_function("document.querySelector('[data-save-state]').textContent.includes('Renderer updated')")
            assert page.evaluate('window.slidekitAssetRevision') == latest
            assert state.read_bytes() == stored
            draft = page.evaluate("JSON.parse(localStorage.getItem('slidekit-conflict-draft:'+location.pathname))")
            assert draft['local']['overlays']['two-tables']['primary-cell']['text'] == 'Retain this unsaved edit'
            page.screenshot(path=str(args.output / 'draft-retained.png'))
            stop(running)  # Forked servers must release inherited browser pipes before browser.close().
            browser.close()
        receipt = {'ok': True, 'open_tab_upgrade': True, 'selected_table_count': 1,
                   'route_preserved': True, 'unsaved_draft_preserved': True, 'stale_edits_applied': False}
        (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps(receipt))
    finally: stop(running)


if __name__ == '__main__': main()

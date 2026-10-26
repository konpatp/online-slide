"""Retained editor font scaling is independent of annotation component names."""
# browser-check: scratch-output
import argparse
import json
from pathlib import Path
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
import server
from test_annotations import fixture
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        sources = root / 'slides'
        sources.mkdir()
        spec = fixture()
        ids = ['human-note', 'text-box-scale-proof']
        for index, component_id in enumerate(ids):
            spec['components'][component_id] = {'kind': 'text', 'text': 'Same scale',
                'region': {'x': 900, 'y': 650 + index * 180, 'width': 700, 'height': 150}}
        spec['annotations'] = [{'kind': 'text', 'component': key} for key in ids]
        (sources / 'plot.json').write_text(json.dumps(spec))
        seed = root / 'seed.json'
        seed.write_text(json.dumps({'schema': 'online-slide/state@4', 'revision': 0,
            'order': [], 'hidden': [], 'objects': {}, 'tables': {},
            'overlays': {spec['id']: {key: {'fontScale': 1.5} for key in ids}}}))
        http = server.make_server(ROOT / 'public', sources, seed, root / 'state.json', root / 'uploads')
        threading.Thread(target=http.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                try:
                    page = browser.new_page(viewport={'width': 1920, 'height': 1080})
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto('http://%s:%s/' % http.server_address, wait_until='networkidle')
                    page.locator('[data-component-id="human-note"]').wait_for()
                    sizes = page.locator('.slide-annotation-text').evaluate_all(
                        'es => es.map(e => parseFloat(getComputedStyle(e).fontSize))')
                    assert sizes == [60, 60], sizes
                    assert not errors, errors
                    page.screenshot(path=str(output / 'font-scale.png'))
                    (output / 'receipt.json').write_text(json.dumps({'ok': True,
                        'retainedFontScale': 1.5, 'computedFontSizes': sizes, 'errors': errors}, indent=2))
                finally:
                    browser.close()
        finally:
            http.shutdown()
            http.server_close()
    print('PASS retained annotation font scale is independent of component ID')


if __name__ == '__main__':
    main()

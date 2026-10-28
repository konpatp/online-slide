"""segment-chain: a still first frame, no autoplay, and one Play that runs once and stops."""
# browser-check: scratch
import json
from pathlib import Path
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT)]
import server
from playwright.sync_api import sync_playwright

SPEC = {'schema': 'online-slide/slide@1', 'id': 'chain-proof', 'recipe': 'segment-chain',
        'createdAt': '2026-10-27', 'headline': 'headline',
        'components': {'headline': {'kind': 'text', 'text': 'One chain'},
                       'play': {'kind': 'text', 'text': 'Play'}, 'replay': {'kind': 'text', 'text': 'Replay'},
                       'counter': {'kind': 'text', 'text': 'step'}},
        'data': {'nodes': 5, 'arrows': True,
                 'groups': [{'rows': [{'frames': [[0, 1], [2, 3], [1, 4]]}]}],
                 'play': {'label': 'play', 'replay': 'replay', 'counter': 'counter', 'intervalMs': 300}}}
SUPERVISED = "e => e.map(x => x.classList.contains('supervised'))"


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / 'slides').mkdir()
        (root / 'slides' / 'chain.json').write_text(json.dumps(SPEC))
        seed = root / 'seed.json'
        seed.write_text(json.dumps({'schema': 'online-slide/state@4', 'revision': 0, 'order': [],
                                    'hidden': [], 'objects': {}, 'tables': {}, 'overlays': {}}))
        http = server.make_server(ROOT / 'public', root / 'slides', seed, root / 'state.json', root / 'uploads')
        threading.Thread(target=http.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                try:
                    page = browser.new_page(viewport={'width': 1920, 'height': 1080})
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto('http://%s:%s/' % http.server_address, wait_until='networkidle')
                    page.locator('.chain-play').wait_for()
                    dots = lambda: page.locator('.chain-dot').evaluate_all(SUPERVISED)
                    assert dots() == [True, True, False, False, False], dots()
                    assert page.locator('.chain-seg.supervised').count() == 1
                    page.wait_for_timeout(1200)  # no autoplay
                    assert dots() == [True, True, False, False, False], 'autoplay ran'
                    page.locator('.chain-play').click()
                    page.wait_for_function("document.querySelector('.chain-play').textContent.includes('Replay')")
                    assert dots() == [False, True, False, False, True], dots()  # endpoints only
                    assert page.locator('.chain-dot.interior').count() == 2, 'interior states must be hollow'
                    page.wait_for_timeout(900)  # the sequence stopped on its last frame
                    assert dots() == [False, True, False, False, True], 'sequence kept running'
                    assert not errors, errors
                finally:
                    browser.close()
        finally:
            http.shutdown()
            http.server_close()
    print('PASS segment-chain starts still, never autoplays, and Play runs once')


if __name__ == '__main__':
    main()

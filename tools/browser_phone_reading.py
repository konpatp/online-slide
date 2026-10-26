"""One reader lifecycle: actual touch, all corners, review URL and unchanged state."""
# browser-check: scratch-output
import argparse
import hashlib
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


def geometry(page):
    return page.locator('[data-stage]').evaluate('''stage => {
      const wrap=stage.parentElement, box=stage.getBoundingClientRect(), frame=wrap.getBoundingClientRect();
      const label=stage.querySelector('.x-axis-label');
      return {scale:Number(stage.dataset.stageScale), mode:stage.dataset.stageFit,
        width:box.width,height:box.height,left:wrap.scrollLeft,top:wrap.scrollTop,
        leftEdge:box.left-frame.left,rightEdge:box.right-frame.left,
        topEdge:box.top-frame.top,bottomEdge:box.bottom-frame.top,
        scrollWidth:wrap.scrollWidth,scrollHeight:wrap.scrollHeight,
        clientWidth:wrap.clientWidth,clientHeight:wrap.clientHeight,
        labelCssPx:parseFloat(getComputedStyle(label).fontSize)*Number(stage.dataset.stageScale)};
    }''')


def touch(cdp, kind, points):
    cdp.send('Input.dispatchTouchEvent', {'type': kind, 'touchPoints': [
        {'id': i, 'x': x, 'y': y} for i, (x, y) in enumerate(points)]})


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
        (sources / 'plot.json').write_text(json.dumps(spec))
        seed = root / 'seed.json'
        seed.write_text(json.dumps({'schema': 'online-slide/state@4', 'revision': 0,
            'order': [], 'hidden': [], 'objects': {}, 'tables': {}, 'overlays': {}}))
        state = root / 'state.json'
        http = server.make_server(ROOT / 'public', sources, seed, state, root / 'uploads')
        threading.Thread(target=http.serve_forever, daemon=True).start()
        errors, writes = [], []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                try:
                    phone = browser.new_context(viewport={'width': 390, 'height': 844},
                        is_mobile=True, has_touch=True, device_scale_factor=2)
                    page = phone.new_page()
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    phone.on('request', lambda r: writes.append(r.method) if r.method not in ('GET', 'HEAD') else None)
                    url = 'http://%s:%s/?present=1#%s' % (*http.server_address, spec['id'])
                    page.goto(url, wait_until='networkidle')
                    page.locator('.x-axis-label').wait_for()
                    before_state = hashlib.sha256(state.read_bytes()).hexdigest()
                    fit = geometry(page)
                    assert abs(fit['width'] - 390) < 1, fit
                    page.locator('[data-reading-toggle]:visible').click()
                    page.wait_for_function("document.querySelector('[data-stage]').dataset.stageFit==='reading'")
                    read = geometry(page)
                    assert read['labelCssPx'] >= 12 and read['scale'] >= .5, read
                    assert read['scrollWidth'] + 1 >= read['width'], read
                    assert 0 <= read['leftEdge'] <= 20 and 0 <= read['topEdge'] <= 68, read
                    cdp = phone.new_cdp_session(page)
                    touch(cdp, 'touchStart', [(310, 420)])
                    for x in (260, 210, 150, 80):
                        touch(cdp, 'touchMove', [(x, 420)])
                        page.wait_for_timeout(20)
                    touch(cdp, 'touchEnd', [])
                    assert geometry(page)['left'] > 100, geometry(page)
                    page.screenshot(path=str(output / 'phone-pan.png'))
                    touch(cdp, 'touchStart', [(140, 400), (240, 400)])
                    for points in ([(120, 400), (260, 400)], [(90, 390), (290, 410)]):
                        touch(cdp, 'touchMove', points)
                        page.wait_for_timeout(20)
                    touch(cdp, 'touchEnd', [])
                    page.wait_for_function("Number(document.querySelector('[data-stage]').dataset.stageScale)>.8")
                    pinch = geometry(page)
                    assert pinch['scale'] > read['scale'], pinch
                    for dx, dy, count in [(230, 0, 10), (0, 320, 6)]:
                        for _ in range(count):
                            touch(cdp, 'touchStart', [(310, 600)])
                            touch(cdp, 'touchMove', [(310 - dx / 2, 600 - dy / 2)])
                            touch(cdp, 'touchMove', [(310 - dx, 600 - dy)])
                            touch(cdp, 'touchEnd', [])
                    corner = geometry(page)
                    assert corner['left'] >= corner['scrollWidth'] - corner['clientWidth'] - 2, corner
                    assert corner['top'] >= corner['scrollHeight'] - corner['clientHeight'] - 2, corner
                    assert 0 < corner['rightEdge'] <= corner['clientWidth'], corner
                    assert 0 < corner['bottomEdge'] <= corner['clientHeight'], corner
                    page.keyboard.press('ArrowLeft')
                    assert geometry(page)['left'] < corner['left']
                    page.keyboard.press('ArrowRight')
                    assert page.evaluate('location.hash') == '#' + spec['id']
                    page.screenshot(path=str(output / 'phone-bottom-right.png'))
                    page.wait_for_function("Number(new URL(location.href).searchParams.get('x'))>0 && Number(new URL(location.href).searchParams.get('y'))>0")
                    review_url = page.url
                    review = phone.new_page()
                    review.on('pageerror', lambda error: errors.append(str(error)))
                    review.goto(review_url, wait_until='networkidle')
                    review.locator('.x-axis-label').wait_for()
                    restored = geometry(review)
                    assert abs(restored['left'] - corner['left']) <= 3 and abs(restored['top'] - corner['top']) <= 3, (restored, corner)
                    review.screenshot(path=str(output / 'phone-review-url.png'))
                    desktop = browser.new_page(viewport={'width': 1280, 'height': 1000})
                    desktop.on('pageerror', lambda error: errors.append(str(error)))
                    desktop.on('request', lambda r: writes.append(r.method) if r.method not in ('GET', 'HEAD') else None)
                    desktop.goto(url, wait_until='networkidle')
                    desktop.locator('.x-axis-label').wait_for()
                    desktop_fit = geometry(desktop)
                    desktop.locator('[data-reading-toggle]:visible').click()
                    reading_scale = geometry(desktop)['scale']
                    desktop.get_by_role('button', name='Zoom in', exact=True).click()
                    assert geometry(desktop)['scale'] > reading_scale
                    desktop.locator('[data-reading-toggle]:visible').click()
                    desktop.wait_for_function("document.querySelector('[data-stage]').dataset.stageFit==='uniform-contain'")
                    desktop_after = geometry(desktop)
                    assert all(desktop_fit[key] == desktop_after[key] for key in ('scale', 'width', 'height')), (desktop_fit, desktop_after)
                    desktop.screenshot(path=str(output / 'desktop-fit.png'))
                    canonical = browser.new_page(viewport={'width': 1920, 'height': 1080})
                    canonical.on('pageerror', lambda error: errors.append(str(error)))
                    canonical.goto(url, wait_until='networkidle')
                    canonical.locator('.x-axis-label').wait_for()
                    assert geometry(canonical)['scale'] == 1
                    overlap = canonical.locator('.reading-controls').evaluate('''controls => {
                        const c=controls.getBoundingClientRect();
                        return [...document.querySelectorAll('.slide-canvas .slide-kicker,.slide-canvas .slide-title')].some(node => {
                            const text=document.createTreeWalker(node,NodeFilter.SHOW_TEXT);
                            while(text.nextNode()) {
                                if(!text.currentNode.textContent.trim()) continue;
                                const range=document.createRange();range.selectNodeContents(text.currentNode);
                                if([...range.getClientRects()].some(b =>
                                    Math.min(c.right,b.right)-Math.max(c.left,b.left)>1 &&
                                    Math.min(c.bottom,b.bottom)-Math.max(c.top,b.top)>1)) return true;
                            }
                            return false;
                        });
                    }''')
                    assert not overlap, 'reader controls must leave the canonical headline and kicker clear'
                    canonical.screenshot(path=str(output / 'desktop-canonical.png'))
                    assert hashlib.sha256(state.read_bytes()).hexdigest() == before_state
                    assert not errors and not writes, (errors, writes)
                    (output / 'receipt.json').write_text(json.dumps({'ok': True, 'phone': {
                        'fit': fit, 'read': read, 'pinch': pinch, 'bottomRight': corner, 'restored': restored},
                        'desktopFit': desktop_after, 'canonicalScale': 1, 'canonicalHeaderClear': True, 'reviewQuery': review_url.split('?', 1)[1],
                        'humanStateSha256': before_state, 'humanStateUnchanged': True,
                        'touchTransport': 'native CDP touch events', 'writes': writes, 'errors': errors}, indent=2))
                finally:
                    browser.close()
        finally:
            http.shutdown()
            http.server_close()
    print('PASS phone reader touch, complete figure reachability, review URL and unchanged human state')


if __name__ == '__main__':
    main()

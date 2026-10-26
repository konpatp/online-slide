#!/usr/bin/env python3
# browser-check: scratch
"""Reject clipped axis titles and keep native scientific selectors readable."""
import json
from pathlib import Path
import sys
import tempfile
import threading

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server import make_server
from review_deck import CHART_AUDIT
from playwright.sync_api import sync_playwright


def main():
    source={"schema":"online-slide/slide@1","id":"synthetic-audience-chart","recipe":"chart-panels",
            "createdAt":"2030-01-01T00:00:00Z","headline":"headline",
            "components":{"headline":{"kind":"text","text":"Synthetic chart audience geometry"},
              "view":{"kind":"text","text":"View"},"first":{"kind":"text","text":"First"},
              "second":{"kind":"text","text":"Second"},
              "chart":{"kind":"chart","figure":{"data":[{"uid":"synthetic-curve","type":"scatter","mode":"lines","x":[0,1,2],"y":[1,2,3]}],
                "layout":{"margin":{"l":120,"r":30,"t":30,"b":90},
                  "xaxis":{"title":{"text":"Synthetic x coordinate "*30,"font":{"size":38}}},
                  "yaxis":{"title":{"text":"Synthetic y coordinate "*30,"font":{"size":38}}}}}}},
            "data":{"panels":[{"chart":"chart"}],
              "selectors":[{"id":"view","label":"view","options":[{"value":"first","label":"first"},{"value":"second","label":"second"}]}],
              "views":[{"selection":{"view":v},"panels":[{"chart":"chart"}]} for v in ("first","second")]}}
    with tempfile.TemporaryDirectory(prefix='chart-audience-') as temp:
        root=Path(temp);slides=root/'slides';slides.mkdir()
        (slides/'synthetic-audience-chart.json').write_text(json.dumps(source))
        http=make_server(ROOT/'public',slides,root/'absent-seed.json',root/'state.json')
        thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch();page=browser.new_page(viewport={"width":1920,"height":1080})
                page.goto(f'http://127.0.0.1:{http.server_address[1]}/?present=1',wait_until='networkidle')
                page.get_by_role('button',name='Second',exact=True).click()
                page.wait_for_selector('[data-chart-ready="true"]')
                clipped=page.evaluate(CHART_AUDIT,4)
                assert any('axis title clipped' in f and 'Synthetic x' in f for f in clipped),clipped
                assert any('axis title clipped' in f and 'Synthetic y' in f for f in clipped),clipped
                page.locator('.native-chart').evaluate("c=>Plotly.relayout(c,{'xaxis.title.text':'Synthetic x','yaxis.title.text':'Synthetic y'})")
                clear=page.evaluate(CHART_AUDIT,4)
                assert not clear,clear
                fonts=page.locator('.native-chart-controls').evaluate("h=>[...h.querySelectorAll('.gallery-selector-label,button')].map(n=>parseFloat(getComputedStyle(n).fontSize))")
                assert fonts and min(fonts)>=35,fonts
                browser.close()
        finally:
            http.shutdown();http.server_close();thread.join()
    print(json.dumps({'ok':True,'clipped_titles_rejected':2,'minimum_selector_font_px':min(fonts)}))


if __name__=='__main__':
    main()

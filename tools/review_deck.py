#!/usr/bin/env python3
"""Capture selected slides and their seams in one browser; never edit live state."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
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


@contextmanager
def serving(args):
    if args.url:
        yield args.url.rstrip("/")
        return
    root = args.root.resolve()
    with tempfile.TemporaryDirectory(prefix="slide-review-") as temporary:
        http = make_server(root / "public", root / "slides",
                           args.state or root / "data/seed-state.json",
                           Path(temporary) / "state.json")
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{http.server_address[1]}"
        finally:
            http.shutdown()
            http.server_close()
            thread.join()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--url")
    parser.add_argument("--state", type=Path, help="read-only seed for local human-overlay review")
    select = parser.add_mutually_exclusive_group(required=True)
    select.add_argument("--slide", action="append")
    select.add_argument("--all", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    findings, captures = [], {}
    with serving(args) as base, sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.on("pageerror", lambda error: findings.append(str(error)))
        page.goto(base + "/", wait_until="networkidle")
        state = page.evaluate("fetch('api/deck-state').then(r => r.json())")
        order = state["order"]
        requested = order if args.all else args.slide
        unknown = set(requested) - set(order)
        if unknown:
            raise ValueError(f"unpublished slide ids: {sorted(unknown)}")
        selected = set(requested)
        visible = [key for key in order if key not in state["hidden"]]
        for key in requested:
            sequence = visible if key in visible else order
            index = sequence.index(key)
            selected.update(sequence[max(0, index-1):index+2])
        for key in (key for key in order if key in selected):
            page.goto(base + "/?present=1#" + key, wait_until="networkidle")
            page.wait_for_function("""() => document.fonts.status === 'loaded' &&
              document.querySelector('.slide-canvas') &&
              [...document.images].every(i => i.complete) &&
              [...document.querySelectorAll('.native-chart')].every(c => c.dataset.chartReady === 'true' || c.dataset.chartError)""")
            page.wait_for_timeout(180)
            audit = page.evaluate("""() => {
              const canvas=document.querySelector('.slide-canvas');
              const c=canvas.getBoundingClientRect();
              const errors=[];
              for (const n of document.querySelectorAll('.native-chart')) {
                if (n.dataset.chartReady!=='true') errors.push('native chart failed: '+n.dataset.chartId);
                const bounds=n.getBoundingClientRect();
                for(const label of n.querySelectorAll('.annotation-text')) {
                  const r=label.getBoundingClientRect();
                  if(r.width && r.height && (r.left<bounds.left-1 || r.right>bounds.right+1 || r.top<bounds.top-1 || r.bottom>bounds.bottom+1))
                    errors.push('chart annotation clipped: '+n.dataset.chartId+' / '+label.textContent);
                }
              }
              if (canvas.clientWidth!==1920 || canvas.clientHeight!==1080)
                errors.push('canonical canvas missing');
              if (c.left < -1 || c.top < -1 || c.right > innerWidth+1 || c.bottom > innerHeight+1)
                errors.push('canvas clipped');
              for (const n of document.querySelectorAll('.semantic-component')) {
                const r=n.getBoundingClientRect();
                if (!r.width || !r.height) continue;
                if (r.left<c.left-1 || r.right>c.right+1 || r.top<c.top-1 || r.bottom>c.bottom+1)
                  errors.push('component outside canvas: '+n.dataset.componentId);
              }
              for (const n of document.querySelectorAll('[data-fit-overflow="true"]'))
                errors.push('text fit overflow: '+(n.dataset.componentId||n.className));
              for (const n of document.querySelectorAll('[data-latex-source]'))
                if (n.dataset.mathEngine!=='katex') errors.push('unrendered math');
              for (const n of document.images)
                if (!n.naturalWidth) errors.push('missing image: '+n.src);
              return {errors, canvas:{x:c.x,y:c.y,width:c.width,height:c.height},
                components:document.querySelectorAll('.semantic-component').length};
            }""")
            path = args.output / (key + ".png")
            page.screenshot(path=str(path))
            captures[key] = {"png": str(path), **audit}
            findings.extend(key + ": " + error for error in audit["errors"])
        browser.close()
    receipt = {"schema": "online-slide/render-review@1", "ok": not findings,
               "sourceRevision": state["sourceRevision"], "stateRevision": state["revision"],
               "order": order, "hidden": state["hidden"], "requested": requested,
               "captures": captures, "findings": findings,
               "elapsedSeconds": round(time.perf_counter()-started, 2)}
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

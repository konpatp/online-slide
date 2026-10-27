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
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


# Chart legibility (PI 2026-10-22: "too cluttered fix. never do this again"):
# a panel draws at most MAX_SERIES data series, and no drawn label or
# annotation may overlap another label or a data marker. Measured on the
# rendered chart, so it sees what the reader sees.
MAX_SERIES = 4
CHART_AUDIT = """(maxSeries) => {
  const errors = [], s = document.querySelector('.slide-canvas').getBoundingClientRect().width / 1920;
  const visible = t => t.visible !== false && t.visible !== 'legendonly';
  const isSeries = t => t.type === 'bar' || ((!t.type || /^scatter/.test(t.type)) && /lines|markers/.test(t.mode || 'lines+markers'));
  for (const chart of document.querySelectorAll('.slide-canvas .native-chart')) {
    const id = chart.dataset.chartId || 'chart', panels = {};
    for (const node of chart.querySelectorAll('.g-xtitle text,.g-ytitle text')) {
      const svg = node.closest('svg.main-svg');
      if (!svg || getComputedStyle(svg).overflow === 'visible') continue;
      const r = node.getBoundingClientRect(), bounds = svg.getBoundingClientRect();
      if (r.width && r.height && (r.left < bounds.left - s || r.right > bounds.right + s || r.top < bounds.top - s || r.bottom > bounds.bottom + s))
        errors.push(`chart axis title clipped: ${id} / ${node.textContent.slice(0,80)}`);
    }
    for (const t of (chart._fullData || chart.data || []).filter(visible).filter(isSeries)) {
      const key = (t.xaxis || 'x') + (t.yaxis || 'y');
      (panels[key] = panels[key] || []).push(t);
    }
    for (const [key, traces] of Object.entries(panels)) {
      const references = traces.filter(t => (t.meta || {}).role === 'reference').length;
      const series = traces.length - Math.min(1, references);
      if (series > maxSeries) errors.push(`chart clutter: ${id} panel ${key} draws ${series} data series (limit ${maxSeries}; one line may be declared meta.role="reference"); split it into small multiples, one panel per group with at most ~3 lines each`);
    }
    // Drawn boxes in canonical pixels; text boxes trimmed to their glyphs.
    const box = (node, trim) => {
      const r = node.getBoundingClientRect(); if (!r.width || !r.height) return null;
      const dy = r.height * trim;
      return {l: r.left / s, r: r.right / s, t: (r.top + dy) / s, b: (r.bottom - dy) / s};
    };
    const overlap = (a, b) => Math.min(a.r, b.r) - Math.max(a.l, b.l) > 1.5 && Math.min(a.b, b.b) - Math.max(a.t, b.t) > 1.5;
    const labels = [], markers = [];
    for (const trace of chart.querySelectorAll('.scatterlayer .trace')) {
      const curve = (trace.__data__ && trace.__data__[0] && trace.__data__[0].trace) || {};
      trace.querySelectorAll('.textpoint text').forEach(node => {
        const b = box(node, .18); if (b) labels.push({b, text: node.textContent, curve: curve.index, point: (node.parentNode.__data__ || {}).i});
      });
      trace.querySelectorAll('.points path.point').forEach(node => {
        const b = box(node, 0); if (b) markers.push({b, curve: curve.index, point: (node.__data__ || {}).i});
      });
    }
    chart.querySelectorAll('.annotation-text').forEach(node => {
      const b = box(node, .18); if (b && node.textContent.trim()) labels.push({b, text: node.textContent, curve: null, point: null});
    });
    const ticks = [...chart.querySelectorAll('g[class$="tick"] text')]
      .map(node => ({b: box(node, 0), text: node.textContent})).filter(tick => tick.b);
    const name = l => JSON.stringify(l.text.trim().slice(0, 40));
    for (let i = 0; i < labels.length; i++) {
      for (let j = i + 1; j < labels.length; j++)
        if (overlap(labels[i].b, labels[j].b)) errors.push(`chart labels collide: ${id} ${name(labels[i])} overlaps ${name(labels[j])}`);
      for (const m of markers)
        if (!(m.curve === labels[i].curve && m.point === labels[i].point) && overlap(labels[i].b, m.b)) {
          errors.push(`chart label covers a data marker: ${id} ${name(labels[i])}`); break;
        }
      for (const tick of ticks)
        if (overlap(labels[i].b, tick.b)) {
          errors.push(`chart label covers an axis tick: ${id} ${name(labels[i])} / ${name(tick)}`); break;
        }
    }
  }
  for (const node of document.querySelectorAll('.native-chart-controls .gallery-selector-label,.native-chart-controls .gallery-option-row button')) {
    if (parseFloat(getComputedStyle(node).fontSize) < 35)
      errors.push(`scientific chart selector text below audience size: ${node.textContent}`);
  }
  return errors;
}"""


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
        page.on("pageerror", lambda error: findings.append(f"{page.url}: {error.stack or error}"))
        page.goto(base + "/?present=1", wait_until="networkidle")
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
        sequence=[key for key in order if key in selected]
        # One live document: fresh page.goto per slide never tests destruction
        # of the preceding chart, nor late work from an abandoned renderer.
        transitions=[]
        for key in sequence + sequence[:1]:
            # Hidden slides are authoring-only. Review them in the editor,
            # never add a production bypass to the audience visibility rule.
            presenting=page.locator('body').evaluate("el=>el.classList.contains('present-only')")
            if presenting != (key not in state['hidden']):
                page.locator('[data-presentation-exit]' if presenting else '[data-fullscreen-toggle]').click(force=True)
            page.evaluate("id => {location.hash=id}",key)
            try:
                page.wait_for_function("""id => document.fonts.status === 'loaded' &&
              document.querySelector('.slide-canvas')?.dataset.slideId === id &&
              [...document.querySelectorAll('.slide-canvas img')].every(i => i.complete) &&
              [...document.querySelectorAll('.native-chart')].every(c => c.dataset.chartReady === 'true' || c.dataset.chartError)""", arg=key, timeout=20000)
            except PlaywrightTimeout:
                findings.append(key+': navigation did not produce a complete slide')
                page.screenshot(path=str(args.output/(key+'.failed.png')))
                break
            transitions.append(key)
            # Audit a fixed point, not a fixed delay: mode switches refit the
            # stage and diagrams relayout over several frames, so one sample
            # after 180 ms occasionally caught a label mid-move.
            page.evaluate("window.__reviewGeometry = null")
            try:
                page.wait_for_function("""() => {
                  const c=document.querySelector('.slide-canvas').getBoundingClientRect();
                  const sig=[c.x,c.y,c.width,c.height].concat(...[...document.querySelectorAll('.semantic-component')]
                    .map(n=>{const r=n.getBoundingClientRect();return [r.x,r.y,r.width,r.height];}))
                    .map(v=>Math.round(v)).join(',');
                  const settled=window.__reviewGeometry===sig; window.__reviewGeometry=sig; return settled;
                }""", polling=150, timeout=5000)
            except PlaywrightTimeout:
                findings.append(key+': layout did not settle within 5 s')
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
              for (const n of document.querySelectorAll('.slide-canvas img'))
                if (!n.naturalWidth) errors.push('missing image: '+n.src);
              return {errors, canvas:{x:c.x,y:c.y,width:c.width,height:c.height},
                components:document.querySelectorAll('.semantic-component').length};
            }""")
            audit["errors"].extend(page.evaluate(CHART_AUDIT, MAX_SERIES))
            path = args.output / (key + ".png")
            page.screenshot(path=str(path))
            captures[key] = {"png": str(path), **audit}
            findings.extend(key + ": " + error for error in audit["errors"])
        browser.close()
    receipt = {"schema": "online-slide/render-review@1", "ok": not findings,
               "sourceRevision": state["sourceRevision"], "stateRevision": state["revision"],
               "order": order, "hidden": state["hidden"], "requested": requested,
               "captures": captures, "findings": findings,
               "navigation": {"mode":"same-document", "visited":transitions,
                              "complete":transitions==sequence+sequence[:1]},
               "elapsedSeconds": round(time.perf_counter()-started, 2)}
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

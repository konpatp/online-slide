#!/usr/bin/env python3
"""Exercise the real browser editor and capture every recipe at 1920x1080.

Playwright is an optional acceptance dependency; the server and ordinary test
suite remain standard-library only.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server  # noqa: E402


SLIDES = [
    "mock-growth-trajectories",
    "mock-angle-evidence",
    "mock-vector-construction",
    "mock-matched-gallery",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "browser-smoke")
    args = parser.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is required only for this optional browser acceptance check.", file=sys.stderr)
        return 2

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    findings: list[str] = []
    captures: dict[str, str] = {}
    timings: dict[str, float] = {}

    with tempfile.TemporaryDirectory() as temp:
        temp_root = Path(temp)
        slides_root = temp_root / "slides"
        shutil.copytree(ROOT / "slides", slides_root)
        http = server.make_server(
            ROOT / "public", slides_root, ROOT / "data" / "seed-state.json",
            temp_root / "state.json", temp_root / "uploads",
        )
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        host, port = http.server_address
        base = f"http://{host}:{port}"
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1920, "height": 1080})

                # Physical edit/save/reload proof on a semantic text leaf.
                page.goto(base + "/#mock-growth-trajectories", wait_until="networkidle")
                page.locator("[data-edit-toggle]").click()
                headline = page.locator('[data-component-id="headline"]')
                headline.click()
                headline.fill("Edited headline survives a source-independent rebuild")
                page.locator('[data-color="#0f9d78"]').click()
                page.locator('[data-font-delta="-0.1"]').click()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                page.reload(wait_until="networkidle")
                edited = page.locator('[data-component-id="headline"]')
                if edited.text_content() != "Edited headline survives a source-independent rebuild":
                    findings.append("semantic headline edit did not survive reload")
                if "15, 157, 120" not in edited.evaluate("node => getComputedStyle(node).color"):
                    findings.append("semantic headline color did not survive reload")

                # Insert and reorder an unrelated source sibling. The saved
                # semantic target must remain attached after the source hash changes.
                plot_path = slides_root / "01-hero-plot.json"
                plot_spec = json.loads(plot_path.read_text(encoding="utf-8"))
                plot_spec["components"] = {
                    "review-note": {"kind": "text", "text": "Unrelated source sibling", "role": "annotation"},
                    **plot_spec["components"],
                }
                plot_path.write_text(json.dumps(plot_spec, indent=2) + "\n", encoding="utf-8")
                page.reload(wait_until="networkidle")
                if page.locator('[data-component-id="headline"]').text_content() != "Edited headline survives a source-independent rebuild":
                    findings.append("semantic headline edit moved after an unrelated source insertion")

                # A human order gesture persists independently of slide source.
                page.locator("[data-edit-toggle]").click()
                first_id = page.locator(".thumb").first.get_attribute("data-id")
                page.locator(".thumb").first.locator('[data-action="move"][data-delta="1"]').click()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                page.reload(wait_until="networkidle")
                if page.locator(".thumb").nth(1).get_attribute("data-id") != first_id:
                    findings.append("human slide move did not survive reload")

                # A real external-file drop becomes a durable content-addressed asset.
                page.goto(base + "/#mock-matched-gallery", wait_until="networkidle")
                page.locator("[data-edit-toggle]").click()
                page.evaluate("""() => {
                  const encoded = "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxMDAgMTAwIj48cmVjdCB3aWR0aD0iMTAwIiBoZWlnaHQ9IjEwMCIgcng9IjE4IiBmaWxsPSIjMGY5ZDc4Ii8+PC9zdmc+";
                  const bytes = Uint8Array.from(atob(encoded), c => c.charCodeAt(0));
                  const transfer = new DataTransfer();
                  transfer.items.add(new File([bytes], "replacement.svg", {type: "image/svg+xml"}));
                  document.querySelector('[data-component-id="image-01-a"]').dispatchEvent(
                    new DragEvent("drop", {bubbles: true, cancelable: true, dataTransfer: transfer})
                  );
                }""")
                page.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                page.reload(wait_until="networkidle")
                if "uploads/" not in page.locator('[data-component-id="image-01-a"] img').get_attribute("src"):
                    findings.append("dropped image did not survive reload as a content-addressed asset")

                # Capture the editor and each clean recipe. Geometry checks use actual pixels.
                editor_path = output / "editor-gallery.png"
                page.screenshot(path=str(editor_path))
                captures["editor"] = str(editor_path)
                page.evaluate("""async (order) => {
                  const current = await (await fetch('/api/deck-state', {cache: 'no-store'})).json();
                  const response = await fetch('/api/deck-state', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                      baseRevision: current.revision,
                      baseSourceRevision: current.sourceRevision,
                      snapshot: {schema: current.schema, order, hidden: [], overlays: {}}
                    })
                  });
                  if (!response.ok) throw new Error('could not reset browser acceptance state');
                }""", SLIDES)
                for slide_id in SLIDES:
                    clean = browser.new_page(viewport={"width": 1920, "height": 1080})
                    t0 = time.perf_counter()
                    clean.goto(base + f"/?present=1#{slide_id}", wait_until="networkidle")
                    timings[slide_id] = round((time.perf_counter() - t0) * 1000, 1)
                    path = output / f"{slide_id}.png"
                    clean.screenshot(path=str(path))
                    captures[slide_id] = str(path)
                    geometry = clean.evaluate("""() => {
                      const canvas = document.querySelector('.slide-canvas').getBoundingClientRect();
                      const outside = [...document.querySelectorAll('[data-component-id]')].filter(node => {
                        const box = node.getBoundingClientRect();
                        return box.left < canvas.left - 1 || box.top < canvas.top - 1 ||
                          box.right > canvas.right + 1 || box.bottom > canvas.bottom + 1;
                      }).map(node => node.dataset.componentId);
                      const zero = [...document.querySelectorAll('[data-component-id]')].filter(node => {
                        const box = node.getBoundingClientRect();
                        return box.width < 1 || box.height < 1;
                      }).map(node => node.dataset.componentId);
                      return {outside, zero, recipe: document.querySelector('.slide-canvas').className};
                    }""")
                    if geometry["outside"]:
                        findings.append(f"{slide_id}: components outside canvas: {geometry['outside']}")
                    if geometry["zero"]:
                        findings.append(f"{slide_id}: zero-size components: {geometry['zero']}")
                    if slide_id == "mock-matched-gallery":
                        fits = clean.locator(".gallery-cell img").evaluate_all("nodes => nodes.map(n => getComputedStyle(n).objectFit)")
                        if set(fits) != {"contain"}:
                            findings.append("gallery does not enforce non-cropping contain behavior")
                    clean.close()
                browser.close()
        finally:
            http.shutdown()
            http.server_close()
            thread.join(timeout=2)

    receipt = {
        "schema": "online-slide/browser-receipt@1",
        "ok": not findings,
        "viewport": {"width": 1920, "height": 1080},
        "slides": SLIDES,
        "captures": captures,
        "navigationMs": timings,
        "elapsedSeconds": round(time.perf_counter() - started, 2),
        "checks": [
            "semantic text edit + formatting survives save/reload",
            "semantic edit survives unrelated source insertion and component reorder",
            "human slide order survives save/reload",
            "external image drop persists by content hash",
            "all semantic components remain inside the 16:9 canvas",
            "gallery images use object-fit: contain",
        ],
        "findings": findings,
    }
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

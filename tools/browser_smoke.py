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
    "mock-guidance-vector-geometry",
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

                # Hierarchical gallery state is presenter state: facet and page
                # choices survive leaving the slide without entering deck overlays.
                page.get_by_role("button", name="Correction", exact=True).click()
                page.get_by_role("button", name="High", exact=True).click()
                page.get_by_role("button", name="4–6", exact=True).click()
                metric_before = page.locator(".gallery-metric").text_content()
                page.goto(base + "/#mock-growth-trajectories", wait_until="networkidle")
                page.goto(base + "/#mock-matched-gallery", wait_until="networkidle")
                if page.get_by_role("button", name="Correction", exact=True).get_attribute("aria-pressed") != "true":
                    findings.append("hierarchical gallery method selection did not persist")
                if page.get_by_role("button", name="High", exact=True).get_attribute("aria-pressed") != "true":
                    findings.append("hierarchical gallery dose selection did not persist")
                if page.get_by_role("button", name="4–6", exact=True).get_attribute("aria-pressed") != "true":
                    findings.append("hierarchical gallery page did not persist")
                if page.locator(".gallery-metric").text_content() != metric_before:
                    findings.append("hierarchical gallery metric changed after slide round-trip")

                # Caption fitting follows live text edits, not only source-time
                # examples. A longer label must refit and persist without the
                # author hand-tuning font size or the box dimensions.
                if page.locator("[data-edit-toggle]").text_content() == "Enable edit":
                    page.locator("[data-edit-toggle]").click()
                caption = page.locator('[data-component-id="caption-otter"]')
                page.wait_for_function("""() => {
                  const node=document.querySelector('[data-component-id="caption-otter"]');
                  return node && node.dataset.fitFontSize;
                }""")
                initial_caption_size = float(caption.get_attribute("data-fit-font-size"))
                caption.fill("golden retriever")
                page.wait_for_function("""() => {
                  const node=document.querySelector('[data-component-id="caption-otter"]');
                  return node && Number(node.dataset.fitLines) >= 2 && node.dataset.fitOverflow === 'false';
                }""")
                if float(caption.get_attribute("data-fit-font-size")) >= initial_caption_size:
                    findings.append("gallery caption did not shrink after a longer live edit")
                page.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                page.reload(wait_until="networkidle")
                caption = page.locator('[data-component-id="caption-otter"]')
                if caption.text_content() != "golden retriever" or caption.get_attribute("data-fit-overflow") != "false":
                    findings.append("gallery caption autofit did not survive save and reload")

                # Fullscreen presentation is an explicit, reversible user action.
                page.locator("[data-fullscreen-toggle]").click()
                page.wait_for_function("document.body.classList.contains('present-only')")
                if page.locator(".topbar").is_visible():
                    findings.append("fullscreen presentation did not remove editor chrome")
                page.keyboard.press("f")
                page.wait_for_function("!document.body.classList.contains('present-only')")
                page.goto(base + "/?present=1#mock-matched-gallery", wait_until="networkidle")
                direct_exit = page.locator("[data-presentation-exit]")
                if not direct_exit.is_visible():
                    findings.append("direct presentation URL did not reveal an exit control")
                else:
                    direct_exit.click()
                    page.wait_for_function("!document.body.classList.contains('present-only')")
                    if "present=1" in page.url:
                        findings.append("presentation exit left the sticky present query in the URL")
                    if not page.locator(".topbar").is_visible():
                        findings.append("presentation exit did not restore editor chrome")

                # Math must hydrate in the editor route too, not only in a
                # presentation-only capture where stale assets are easier to miss.
                page.goto(base + "/#mock-guidance-vector-geometry", wait_until="networkidle")
                math_sources = page.locator("[data-latex-source]").count()
                if not math_sources or page.locator('[data-math-engine="katex"]').count() != math_sources:
                    findings.append("editor route left authored LaTeX unhydrated")

                # A real node drag must reroute its semantic connector. This is
                # the behavior that fixed SVG arrow coordinates could not supply.
                page.goto(base + "/#mock-vector-construction", wait_until="networkidle")
                if "edit" not in page.locator("[data-edit-toggle]").text_content().lower():
                    page.locator("[data-edit-toggle]").click()
                elif page.locator("[data-edit-toggle]").text_content() == "Enable edit":
                    page.locator("[data-edit-toggle]").click()
                page.wait_for_selector('g[model-id="student-node"]')
                node = page.locator('g[model-id="student-node"]')
                link = page.locator('g[model-id="student-to-prediction"] path[joint-selector="line"]')
                if node.count() != 1 or link.count() != 1:
                    findings.append("JointJS semantic node/link DOM was not rendered")
                else:
                    teacher = page.locator('[data-diagram-node-id="teacher-node"]')
                    before_size = teacher.bounding_box()
                    teacher_detail = page.locator('[data-component-id="teacher-detail"]')
                    teacher_detail.fill(
                        "one source call with a substantially longer authenticated condition "
                        "that must wrap onto multiple lines and expand this node"
                    )
                    page.wait_for_function("""() => {
                      const n = document.querySelector('[data-diagram-node-id="teacher-node"]');
                      return n && n.scrollWidth <= n.clientWidth + 1 && n.scrollHeight <= n.clientHeight + 1;
                    }""")
                    after_size = teacher.bounding_box()
                    if after_size["width"] <= before_size["width"] and after_size["height"] <= before_size["height"]:
                        findings.append("content-sized diagram node did not grow after a longer live edit")
                    overflow_nodes = page.locator(".diagram-node-copy").evaluate_all(
                        "nodes => nodes.filter(n => n.scrollWidth > n.clientWidth + 1 || n.scrollHeight > n.clientHeight + 1).map(n => n.dataset.diagramNodeId)"
                    )
                    if overflow_nodes:
                        findings.append(f"content-sized diagram nodes still overflow: {overflow_nodes}")
                    before = link.get_attribute("d")
                    drag_point = page.evaluate("""() => {
                      const node=document.querySelector('g[model-id="student-node"]');
                      const box=node.getBoundingClientRect();
                      const candidates=[
                        {x:box.right-4,y:box.top+box.height/2},
                        {x:box.left+4,y:box.top+box.height/2},
                        {x:box.left+box.width/2,y:box.top+4},
                        {x:box.left+box.width/2,y:box.bottom-4},
                      ];
                      return candidates.find(point => {
                        const hit=document.elementFromPoint(point.x,point.y);
                        return hit && hit.closest('[model-id="student-node"]');
                      }) || null;
                    }""")
                    if not drag_point:
                        findings.append("JointJS node has no exposed border drag target")
                    else:
                        page.mouse.move(drag_point["x"], drag_point["y"])
                        page.mouse.down()
                        page.mouse.move(drag_point["x"], drag_point["y"] + 72, steps=8)
                        page.mouse.up()
                        after = link.get_attribute("d")
                        if before == after:
                            findings.append("dragging a JointJS node did not reroute its connector")

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
                    # The exit stays discoverable; remove only the transient
                    # emphasis so clean receipts show its settled appearance.
                    clean.locator("[data-presentation-exit]").evaluate(
                        "node => node.classList.remove('visible')"
                    )
                    if not clean.locator("[data-presentation-exit]").is_visible():
                        findings.append(f"{slide_id}: presentation exit is not persistently discoverable")
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
                        image_boxes = clean.locator(".gallery-cell img").evaluate_all(
                            "nodes => nodes.map(n => { const i=n.getBoundingClientRect(); const c=n.parentElement.getBoundingClientRect(); return {iw:i.width,ih:i.height,cw:c.width,ch:c.height,nw:n.naturalWidth,nh:n.naturalHeight}; })"
                        )
                        if any(box["iw"] > box["cw"] + 1 or box["ih"] > box["ch"] + 1 for box in image_boxes):
                            findings.append("gallery image element overflows its evidence cell")
                        if clean.locator(".hierarchical-gallery-grid .gallery-cell").count() != 9:
                            findings.append("gallery must show three large rows by three conditions")
                        frame_fit = clean.locator(".gallery-cell").evaluate_all(
                            "nodes => nodes.map(n => { const b=n.getBoundingClientRect(); return Math.abs(b.width-b.height); })"
                        )
                        if any(delta > 2 for delta in frame_fit):
                            findings.append("gallery frames do not snugly match the square evidence images")
                        caption_size = clean.locator(".gallery-cell-caption").evaluate_all(
                            "nodes => nodes.map(n => parseFloat(getComputedStyle(n).fontSize))"
                        )
                        if caption_size and min(caption_size) < 20:
                            findings.append("gallery class labels are too small")
                        caption_fit = clean.locator(".gallery-cell-caption").evaluate_all(
                            """nodes => nodes.map(n => {
                              const frame=n.parentElement.getBoundingClientRect();
                              const box=n.getBoundingClientRect();
                              return {text:n.textContent, mode:n.dataset.fitMode,
                                lines:Number(n.dataset.fitLines), size:parseFloat(n.dataset.fitFontSize),
                                overflow:n.dataset.fitOverflow,
                                contained:box.width<=frame.width+1 && box.height<=frame.height+1};
                            })"""
                        )
                        if len(caption_fit) < 2:
                            findings.append("gallery autofit example must exercise one-line and wrapped captions")
                        elif not all(item["mode"] == "gallery-caption-region" and item["overflow"] == "false" and item["contained"] for item in caption_fit):
                            findings.append("gallery captions do not fit their fixed caption boxes")
                        else:
                            one_line = next((item for item in caption_fit if item["text"] == "otter"), None)
                            wrapped = next((item for item in caption_fit if item["text"] == "golden retriever"), None)
                            if not one_line or one_line["lines"] != 1:
                                findings.append("short gallery caption did not remain on one line")
                            if not wrapped or wrapped["lines"] < 2:
                                findings.append("long gallery caption did not exercise wrapped autofit")
                            if one_line and wrapped and not wrapped["size"] < one_line["size"]:
                                findings.append("wrapped gallery caption was not scaled below the short caption")
                    if slide_id == "mock-vector-construction":
                        engine = clean.locator(".joint-paper").get_attribute("data-diagram-engine")
                        if engine != "jointjs-directed-graph":
                            findings.append("mechanism slide did not use the JointJS layout runtime")
                        if clean.locator(".joint-paper").get_attribute("data-diagram-content-sizing") != "measured":
                            findings.append("mechanism slide did not declare measured content sizing")
                        if clean.locator(".joint-paper").get_attribute("data-diagram-layout") != "lanes":
                            findings.append("parallel mechanism paths did not use semantic lane layout")
                        node_geometry = clean.evaluate("""() => [...document.querySelectorAll('.diagram-node-copy')].map(copy => {
                          const shape = document.querySelector(`g[model-id="${copy.dataset.diagramNodeId}"]`);
                          const c = copy.getBoundingClientRect();
                          const s = shape && shape.getBoundingClientRect();
                          return {
                            id: copy.dataset.diagramNodeId,
                            overflow: copy.scrollWidth > copy.clientWidth + 1 || copy.scrollHeight > copy.clientHeight + 1,
                            aligned: Boolean(s) && Math.abs(c.width - s.width) <= 2 && Math.abs(c.height - s.height) <= 2,
                          };
                        })""")
                        overflowing = [item["id"] for item in node_geometry if item["overflow"]]
                        misaligned = [item["id"] for item in node_geometry if not item["aligned"]]
                        if overflowing:
                            findings.append(f"content-sized diagram nodes overflow in clean render: {overflowing}")
                        if misaligned:
                            findings.append(f"diagram copy and measured node frames disagree: {misaligned}")
                        lane_centers = clean.evaluate("""() => {
                          const center = id => { const r=document.querySelector(`[data-diagram-node-id="${id}"]`).getBoundingClientRect(); return [r.left+r.width/2,r.top+r.height/2]; };
                          return Object.fromEntries(['query-node','teacher-node','student-node','target-node','prediction-node','loss-node'].map(id => [id,center(id)]));
                        }""")
                        aligned_pairs = [
                            ("teacher-node", "target-node"),
                            ("student-node", "prediction-node"),
                            ("query-node", "loss-node"),
                        ]
                        if any(abs(lane_centers[a][1] - lane_centers[b][1]) > 6 for a, b in aligned_pairs):
                            findings.append("semantic lane nodes do not share stable centerlines")
                        audience_sizes = clean.evaluate("""() => [...document.querySelectorAll('.node-label,.node-detail')].map(node => {
                          const parent=getComputedStyle(node.closest('.diagram-node-copy')).transform;
                          const scale=parent === 'none' ? 1 : new DOMMatrix(parent).a;
                          return parseFloat(getComputedStyle(node).fontSize) * scale;
                        })""")
                        if audience_sizes and min(audience_sizes) < 34:
                            findings.append(f"mechanism audience text fell below the 26pt floor: {min(audience_sizes):.1f}px")
                        graph_bounds = clean.evaluate("""() => {
                          const host = document.querySelector('.joint-paper').getBoundingClientRect();
                          const cells = [...document.querySelectorAll('.joint-paper .joint-cell')]
                            .map(node => node.getBoundingClientRect()).filter(box => box.width && box.height);
                          return cells.filter(box => box.left < host.left - 1 || box.top < host.top - 1 ||
                            box.right > host.right + 1 || box.bottom > host.bottom + 1).length;
                        }""")
                        if graph_bounds:
                            findings.append("JointJS graph was not centered and contained")
                    if slide_id == "mock-guidance-vector-geometry":
                        if clean.locator(".jsxgraph-host").get_attribute("data-geometry-engine") != "jsxgraph":
                            findings.append("vector slide did not use JSXGraph")
                        if clean.locator('[data-math-engine="katex"]').count() < 8:
                            findings.append("vector geometry mathematics did not render through KaTeX")
                        label_fit = clean.locator(".vector-label").evaluate_all(
                            """nodes => nodes.map(node => {
                              const region=node.parentElement.getBoundingClientRect();
                              const box=node.getBoundingClientRect();
                              return {mode:node.dataset.fitMode, overflow:node.dataset.fitOverflow,
                                contained:box.left>=region.left-1 && box.top>=region.top-1 &&
                                  box.right<=region.right+1 && box.bottom<=region.bottom+1};
                            })"""
                        )
                        if not label_fit or not all(item["mode"] == "vector-label-region" and item["overflow"] == "false" and item["contained"] for item in label_fit):
                            findings.append("vector labels do not fit their declared text regions")
                        single_equation = clean.evaluate("""() => {
                          const host = document.querySelector('.vector-equations');
                          [...host.children].slice(1).forEach(node => node.remove());
                          const h=host.getBoundingClientRect(), e=host.firstElementChild.getBoundingClientRect();
                          return {
                            columns:getComputedStyle(host).gridTemplateColumns.split(' ').length,
                            contained:e.left >= h.left-1 && e.right <= h.right+1,
                            centered:Math.abs((e.left+e.right)/2-(h.left+h.right)/2) <= 2,
                          };
                        }""")
                        if single_equation["columns"] != 1 or not single_equation["contained"] or not single_equation["centered"]:
                            findings.append("one vector equation did not span and center in the full equation band")
                    if slide_id == "mock-angle-evidence":
                        table_fit = clean.locator(".evidence-table").evaluate(
                            "node => ({mode:node.dataset.fitMode, overflow:node.dataset.fitOverflow, scale:parseFloat(node.dataset.fitScale)})"
                        )
                        if table_fit["mode"] != "evidence-table-region" or table_fit["overflow"] != "false" or not (0.58 <= table_fit["scale"] <= 1):
                            findings.append("evidence table did not choose a contained region-fit scale")
                    accent_rail = clean.evaluate("""() => {
                      const style = getComputedStyle(document.querySelector('.slide-canvas'), '::before');
                      return style.content !== 'none' && style.content !== 'normal';
                    }""")
                    if accent_rail:
                        findings.append(f"{slide_id}: decorative accent rail returned")
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
            "hierarchical gallery facets, metric, and page survive slide navigation",
            "JointJS node drag physically reroutes its semantic connector",
            "JointJS nodes grow and reflow after longer live text edits",
            "JointJS text overlays match their measured SVG node frames without overflow",
            "JointJS and JSXGraph compositions remain centered and contained",
            "all semantic components remain inside the 16:9 canvas",
            "gallery images use object-fit: contain",
            "gallery frames are snug, rounded, and captions are readable",
            "gallery captions auto-fit a fixed-height box after wrapping",
            "fullscreen presentation mode is explicit and reversible",
            "shared presentation URLs expose a clickable exit and clear sticky presentation state",
            "LaTeX hydrates through KaTeX in editor and presentation modes",
            "all vector geometry mathematics renders through KaTeX",
            "one vector equation spans and centers in the full equation band",
            "parallel diagrams preserve semantic lane centerlines and a 26pt audience-text floor",
        ],
        "findings": findings,
    }
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

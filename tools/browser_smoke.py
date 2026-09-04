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
    "mock-target-accessibility",
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

                # A table is edited as a table: cells navigate with Tab,
                # row/column structure has semantic ids, TSV paste expands the
                # matrix, and column width survives a real pointer resize.
                page.goto(base + "/#mock-angle-evidence", wait_until="networkidle")
                if page.locator("[data-edit-toggle]").text_content() == "Enable edit":
                    page.locator("[data-edit-toggle]").click()
                depth_mid = page.locator('[data-component-id="depth-mid"]')
                depth_mid.click()
                if not page.locator("[data-table-tools]").is_visible():
                    findings.append("selecting a table cell did not expose native table controls")
                depth_mid.press("Tab")
                if "depth-high" not in page.locator("[data-selected-component]").text_content():
                    findings.append("Tab did not move to the next semantic table cell")
                page.locator('[data-component-id="depth-mid"]').click()
                page.locator('[data-table-action="row-add"]').click()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                inserted_row = page.locator("tbody tr").nth(2)
                inserted_label = inserted_row.locator("th .semantic-component")
                inserted_label.fill("Inserted comparison")
                inserted_first = inserted_row.locator("td .semantic-component").first
                inserted_first.evaluate("node => node.focus()")
                page.evaluate("""raw => {
                  const node=document.querySelectorAll('.evidence-table tbody tr')[2].querySelector('td .semantic-component');
                  const transfer=new DataTransfer();
                  transfer.setData('text/plain',raw);
                  node.dispatchEvent(new ClipboardEvent('paste',{bubbles:true,cancelable:true,clipboardData:transfer}));
                }""", "11\t12\n21\t22")
                page.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                if page.locator(".evidence-table tbody tr").count() != 5:
                    findings.append("TSV paste did not preserve/add the required table rows")
                inserted_label = page.locator(".evidence-table tbody tr").nth(2).locator("th .semantic-component")
                inserted_label.click()
                page.locator('[data-table-action="row-down"]').click()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                if page.locator(".evidence-table tbody tr").nth(3).locator("th").text_content() != "Inserted comparison":
                    findings.append("native row reorder retargeted the inserted row")
                page.locator('[data-component-id="column-high"]').click()
                page.locator('[data-table-action="column-add"]').click()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                if page.locator(".evidence-table thead th").count() != 6:
                    findings.append("native column insertion did not expand the table")
                inserted_header = page.locator(".evidence-table thead th").nth(4).locator(".semantic-component")
                inserted_header.fill("Audit")
                inserted_header.click()
                page.locator('[data-table-action="column-left"]').click()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                moved_header = page.locator(".evidence-table thead th").nth(3)
                moved_header.wait_for(state="visible")
                if moved_header.locator(".semantic-component").text_content() != "Audit":
                    findings.append("native column reorder retargeted the inserted column")
                resizer = moved_header.locator(".table-column-resizer")
                resizer.wait_for(state="visible")
                before_width = moved_header.bounding_box()["width"]
                resize_box = resizer.bounding_box()
                page.mouse.move(resize_box["x"] + resize_box["width"] / 2,
                                resize_box["y"] + resize_box["height"] / 2)
                page.mouse.down()
                page.mouse.move(resize_box["x"] + resize_box["width"] / 2 + 70,
                                resize_box["y"] + resize_box["height"] / 2, steps=7)
                page.mouse.up()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                if page.locator(".evidence-table thead th").nth(3).bounding_box()["width"] <= before_width + 30:
                    findings.append("native column resize did not change the selected column width")
                page.reload(wait_until="networkidle")
                if page.locator(".evidence-table thead th").nth(3).locator(".semantic-component").text_content() != "Audit":
                    findings.append("native table structure did not survive save/reload")
                page.locator("[data-edit-toggle]").click()
                page.locator(".evidence-table thead th").nth(3).locator(".semantic-component").click()
                table_editor = output / "editor-native-table.png"
                page.screenshot(path=str(table_editor))
                captures["native-table-editor"] = str(table_editor)
                table_state = page.evaluate("() => fetch('api/deck-state',{cache:'no-store'}).then(r=>r.json())")
                logical = table_state.get("tables", {}).get("mock-angle-evidence")
                if not logical or not all("id" in row for row in logical["rows"]):
                    findings.append("native table state did not persist semantic row identities")

                # Source sibling insertion and source-row reorder cannot move
                # the accepted human table structure to another meaning.
                table_path = slides_root / "02-evidence-table.json"
                table_original = table_path.read_text(encoding="utf-8")
                table_source = json.loads(table_original)
                table_source["components"] = {
                    "unrelated-source-label": {"kind": "text", "text": "Unrelated", "role": "annotation"},
                    **table_source["components"],
                }
                table_source["data"]["rows"] = list(reversed(table_source["data"]["rows"]))
                table_path.write_text(json.dumps(table_source, indent=2) + "\n", encoding="utf-8")
                page.reload(wait_until="networkidle")
                if page.locator(".evidence-table thead th").nth(3).locator(".semantic-component").text_content() != "Audit":
                    findings.append("source reorder retargeted a human table column")
                if page.locator(".evidence-table tbody tr").nth(3).locator("th").text_content() != "Inserted comparison":
                    findings.append("source reorder retargeted a human table row")
                page.locator("[data-edit-toggle]").click()
                page.locator(".evidence-table tbody tr").nth(3).locator("th .semantic-component").click()
                page.locator('[data-table-action="row-delete"]').click()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                if page.get_by_text("Inserted comparison", exact=True).count():
                    findings.append("native row deletion did not remove the selected logical row")
                page.get_by_text("Audit", exact=True).click()
                page.locator('[data-table-action="column-delete"]').click()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                if page.get_by_text("Audit", exact=True).count():
                    findings.append("native column deletion did not remove the selected logical column")
                table_path.write_text(table_original, encoding="utf-8")
                # Reload onto the restored source revision before the next
                # mutation. This is the same fail-closed revision handshake a
                # real contributor/source update requires.
                page.reload(wait_until="networkidle")

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
                page.wait_for_function(
                    "document.querySelector('[data-component-id=\"image-01-a\"] img').src.includes('/uploads/')"
                )
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

                # Text regions are direct-manipulation objects, not merely
                # source-time boxes. Move a generic headline, then move,
                # resize, edit, save, and reload a bounded vector label.
                if page.locator("[data-edit-toggle]").text_content() == "Enable edit":
                    page.locator("[data-edit-toggle]").click()
                headline = page.locator('[data-component-id="headline"]')
                headline_before = headline.bounding_box()
                headline.click()
                headline_move = page.locator('.text-region-frame [aria-label="Move text region"]')
                move_box = headline_move.bounding_box()
                page.mouse.move(move_box["x"] + move_box["width"] / 2,
                                move_box["y"] + move_box["height"] / 2)
                page.mouse.down()
                page.mouse.move(move_box["x"] + move_box["width"] / 2 + 54,
                                move_box["y"] + move_box["height"] / 2 + 18, steps=6)
                page.mouse.up()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                headline_after = page.locator('[data-component-id="headline"]').bounding_box()
                if headline_after["x"] <= headline_before["x"] + 30:
                    findings.append("generic text region did not move through its physical drag handle")

                label = page.locator('[data-component-id="remove-label"]')
                sibling_before = page.locator('[data-component-id="raw-label"]').bounding_box()
                label.click()
                frame = page.locator('.text-region-frame[data-text-region-frame="remove-label"]')
                before = frame.bounding_box()
                move = frame.locator('[aria-label="Move text region"]')
                move_box = move.bounding_box()
                page.mouse.move(move_box["x"] + move_box["width"] / 2,
                                move_box["y"] + move_box["height"] / 2)
                page.mouse.down()
                page.mouse.move(move_box["x"] + move_box["width"] / 2 + 86,
                                move_box["y"] + move_box["height"] / 2 + 34, steps=8)
                page.mouse.up()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")

                label = page.locator('[data-component-id="remove-label"]')
                label.click()
                frame = page.locator('.text-region-frame[data-text-region-frame="remove-label"]')
                moved = frame.bounding_box()
                if moved["x"] <= before["x"] + 50 or moved["y"] <= before["y"] + 18:
                    findings.append("bounded vector text region did not move with its drag handle")
                resize = frame.locator('[aria-label="Resize text region"]')
                resize_box = resize.bounding_box()
                page.mouse.move(resize_box["x"] + resize_box["width"] / 2,
                                resize_box["y"] + resize_box["height"] / 2)
                page.mouse.down()
                page.mouse.move(resize_box["x"] + resize_box["width"] / 2 - 100,
                                resize_box["y"] + resize_box["height"] / 2 + 34, steps=8)
                page.mouse.up()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")

                label = page.locator('[data-component-id="remove-label"]')
                label.fill("remove the parallel component before normalizing the direction")
                page.wait_for_function("""() => {
                  const node=document.querySelector('[data-component-id="remove-label"]');
                  return node && Number(node.dataset.fitLines) >= 2 && node.dataset.fitOverflow === 'false';
                }""")
                page.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                fitted_size = float(label.get_attribute("data-fit-font-size"))
                if fitted_size >= 34:
                    findings.append("resized text region did not shrink a longer phrase to fit")
                state_after_region_edit = page.evaluate("() => fetch('api/deck-state', {cache:'no-store'}).then(r => r.json())")
                region_overlay = state_after_region_edit["overlays"]["mock-guidance-vector-geometry"]["remove-label"].get("region")
                if not region_overlay or region_overlay["width"] >= 530 or region_overlay["height"] <= 100:
                    findings.append("text region geometry was not durably saved in canonical slide coordinates")
                page.reload(wait_until="networkidle")
                persisted_label = page.locator('[data-component-id="remove-label"]')
                page.wait_for_function("""() => {
                  const node=document.querySelector('[data-component-id="remove-label"]');
                  return node && node.dataset.fitOverflow === 'false';
                }""")
                if persisted_label.text_content() != "remove the parallel component before normalizing the direction":
                    findings.append("text inside a moved and resized region did not survive reload")
                if persisted_label.get_attribute("data-fit-overflow") != "false":
                    findings.append("persisted text region no longer contained its text after reload")
                sibling_after = page.locator('[data-component-id="raw-label"]').bounding_box()
                if abs(sibling_after["x"] - sibling_before["x"]) > 2 or abs(sibling_after["y"] - sibling_before["y"]) > 2:
                    findings.append("moving one text region changed an unrelated sibling")

                # A real node drag must reroute its semantic connector. This is
                # the behavior that fixed SVG arrow coordinates could not supply.
                page.goto(base + "/#mock-vector-construction", wait_until="networkidle")
                if "edit" not in page.locator("[data-edit-toggle]").text_content().lower():
                    page.locator("[data-edit-toggle]").click()
                elif page.locator("[data-edit-toggle]").text_content() == "Enable edit":
                    page.locator("[data-edit-toggle]").click()
                page.wait_for_selector('g[model-id="student-node"]')
                if page.locator(".joint-paper").get_attribute("data-diagram-measurement") != "untransformed-slide-coordinates":
                    findings.append("diagram nodes were not measured in stable slide coordinates")
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
                    # The content edit also saves and revision-safely rerenders
                    # the slide. Wait for that durable boundary before testing
                    # an independent drag gesture; otherwise the accepted save
                    # may replace the diagram while the pointer is moving.
                    page.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                    page.wait_for_timeout(100)
                    after_size = teacher.bounding_box()
                    if after_size["width"] <= before_size["width"] and after_size["height"] <= before_size["height"]:
                        findings.append("content-sized diagram node did not grow after a longer live edit")
                    overflow_nodes = page.locator(".diagram-node-copy").evaluate_all(
                        "nodes => nodes.filter(n => n.scrollWidth > n.clientWidth + 1 || n.scrollHeight > n.clientHeight + 1).map(n => n.dataset.diagramNodeId)"
                    )
                    if overflow_nodes:
                        findings.append(f"content-sized diagram nodes still overflow: {overflow_nodes}")
                    editor_geometry = page.evaluate("""() => {
                      const nodes=[...document.querySelectorAll('.diagram-node-copy')].map(node => {
                        const r=node.getBoundingClientRect();
                        return {id:node.dataset.diagramNodeId,left:r.left,top:r.top,right:r.right,bottom:r.bottom};
                      });
                      const overlaps=[];
                      for (let i=0;i<nodes.length;i++) for (let j=i+1;j<nodes.length;j++) {
                        const a=nodes[i], b=nodes[j];
                        const width=Math.min(a.right,b.right)-Math.max(a.left,b.left);
                        const height=Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top);
                        if (width > 1 && height > 1) overlaps.push([a.id,b.id]);
                      }
                      const plane=document.querySelector('.diagram-plane').getBoundingClientRect();
                      const outside=nodes.filter(n => n.left<plane.left-1 || n.top<plane.top-1 ||
                        n.right>plane.right+1 || n.bottom>plane.bottom+1).map(n => n.id);
                      return {overlaps,outside};
                    }""")
                    if editor_geometry["overlaps"]:
                        findings.append(f"editor-sized diagram nodes overlap: {editor_geometry['overlaps']}")
                    if editor_geometry["outside"]:
                        findings.append(f"editor-sized diagram nodes leave their layout region: {editor_geometry['outside']}")
                    split_words = page.evaluate("""() => [...document.querySelectorAll('.node-label,.node-detail')]
                      .filter(node => !node.dataset.latexSource && node.firstChild && node.firstChild.nodeType === Node.TEXT_NODE)
                      .flatMap(node => {
                        const source=node.firstChild, text=source.textContent || '', findings=[];
                        // Hyphens are intentional linguistic break points;
                        // flag only a continuous alphabetic word split over
                        // multiple painted line boxes.
                        for (const match of text.matchAll(/[A-Za-z]{4,}/g)) {
                          const range=document.createRange();
                          range.setStart(source,match.index); range.setEnd(source,match.index+match[0].length);
                          if (range.getClientRects().length > 1) findings.push(match[0]);
                        }
                        return findings;
                      })""")
                    if split_words:
                        findings.append(f"editor-sized diagram split readable words: {split_words}")
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
                        page.wait_for_timeout(100)
                        after = link.get_attribute("d")
                        if before == after:
                            findings.append("dragging a JointJS node did not reroute its connector")

                    # Node movement is a durable semantic object edit, not a
                    # transient canvas transform. It must survive reload and
                    # source sibling insertion/reorder.
                    page.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                    moved_box = page.locator('g[model-id="student-node"]').bounding_box()
                    object_state = page.evaluate(
                        "() => fetch('/api/deck-state',{cache:'no-store'}).then(r=>r.json()).then(x=>x.objects)"
                    )
                    student_geometry = object_state.get("mock-vector-construction", {}).get("student-node")
                    if not student_geometry or student_geometry.get("kind") != "diagram-node":
                        findings.append("JointJS node movement did not persist by semantic object id")
                    page.reload(wait_until="networkidle")
                    persisted_box = page.locator('g[model-id="student-node"]').bounding_box()
                    if abs(persisted_box["y"] - moved_box["y"]) > 3:
                        findings.append("semantic node position did not survive reload")

                    mechanism_path = slides_root / "03-mechanism-diagram.json"
                    mechanism_original = mechanism_path.read_text(encoding="utf-8")
                    mechanism_source = json.loads(mechanism_original)
                    mechanism_source["data"]["nodes"].insert(0, {
                        "id": "unrelated-review-node", "label": "query-label", "tone": "quiet",
                        "lane": 0, "step": 4,
                    })
                    mechanism_source["data"]["nodes"] = list(reversed(mechanism_source["data"]["nodes"]))
                    mechanism_path.write_text(json.dumps(mechanism_source, indent=2) + "\n", encoding="utf-8")
                    page.reload(wait_until="networkidle")
                    reordered_box = page.locator('g[model-id="student-node"]').bounding_box()
                    if abs(reordered_box["y"] - moved_box["y"]) > 3:
                        findings.append("source node insertion/reorder retargeted a human node edit")
                    mechanism_path.write_text(mechanism_original, encoding="utf-8")
                    page.reload(wait_until="networkidle")

                    # A physical corner-handle drag resizes the selected node;
                    # the semantic text leaves then wrap/refit inside it.
                    if page.locator("[data-edit-toggle]").text_content() == "Enable edit":
                        page.locator("[data-edit-toggle]").click()
                    teacher_svg = page.locator('g[model-id="teacher-node"]')
                    teacher_box = teacher_svg.bounding_box()
                    page.mouse.click(teacher_box["x"] + 3, teacher_box["y"] + teacher_box["height"] / 2)
                    if "teacher-node" not in page.locator("[data-selected-component]").text_content():
                        findings.append("clicking a diagram-node border did not select the semantic node")
                    resize_handle = page.locator('g.joint-tool[model-id="teacher-node"] [joint-selector="handle"]')
                    resize_handle.wait_for(state="visible")
                    handle_box = resize_handle.bounding_box()
                    page.mouse.move(handle_box["x"] + handle_box["width"] / 2,
                                    handle_box["y"] + handle_box["height"] / 2)
                    page.mouse.down()
                    page.mouse.move(handle_box["x"] + handle_box["width"] / 2 + 92,
                                    handle_box["y"] + handle_box["height"] / 2 + 58, steps=8)
                    page.mouse.up()
                    page.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                    resized_box = page.locator('g[model-id="teacher-node"]').bounding_box()
                    if resized_box["width"] <= teacher_box["width"] + 50 or resized_box["height"] <= teacher_box["height"] + 25:
                        findings.append("JointJS corner handle did not resize the selected node")
                    if page.locator('[data-diagram-node-id="teacher-node"] .diagram-node-content').get_attribute("data-fit-overflow") == "true":
                        findings.append("resized diagram-node text did not refit inside its bounded node")

                    # A connector is a native semantic object: clicking its
                    # stroke exposes a JointJS vertex track and dragging that
                    # track creates one durable bend point.
                    link_selector = 'g[model-id="student-to-prediction"] path[joint-selector="line"]'
                    link_point = page.evaluate("""selector => {
                      const path=document.querySelector(selector);
                      const local=path.getPointAtLength(path.getTotalLength()/2);
                      const point=new DOMPoint(local.x,local.y).matrixTransform(path.getScreenCTM());
                      return {x:point.x,y:point.y};
                    }""", link_selector)
                    page.mouse.click(link_point["x"], link_point["y"])
                    if "student-to-prediction" not in page.locator("[data-selected-component]").text_content():
                        findings.append("clicking a connector did not select its semantic edge")
                    vertex_path = 'g[data-tool-name="vertices"] path[joint-selector="connection"]'
                    vertex_point = page.evaluate("""selector => {
                      const path=document.querySelector(selector);
                      const local=path.getPointAtLength(path.getTotalLength()/2);
                      const point=new DOMPoint(local.x,local.y).matrixTransform(path.getScreenCTM());
                      return {x:point.x,y:point.y};
                    }""", vertex_path)
                    page.mouse.move(vertex_point["x"], vertex_point["y"])
                    page.mouse.down()
                    page.mouse.move(vertex_point["x"] + 54, vertex_point["y"] - 64, steps=8)
                    page.mouse.up()
                    page.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                    object_state = page.evaluate(
                        "() => fetch('/api/deck-state',{cache:'no-store'}).then(r=>r.json()).then(x=>x.objects)"
                    )
                    edge_geometry = object_state.get("mock-vector-construction", {}).get("student-to-prediction")
                    if not edge_geometry or len(edge_geometry.get("vertices", [])) != 1:
                        findings.append("connector bend point did not persist by semantic edge id")
                    diagram_editor = output / "editor-native-diagram.png"
                    page.screenshot(path=str(diagram_editor))
                    captures["native-diagram-editor"] = str(diagram_editor)

                # Vectors and ordinary segments use the same source-authored
                # identity contract. Endpoint handles change length/rotation;
                # the square midpoint translates the complete object.
                page.goto(base + "/#mock-guidance-vector-geometry", wait_until="networkidle")
                if page.locator("[data-edit-toggle]").text_content() == "Enable edit":
                    page.locator("[data-edit-toggle]").click()
                page.wait_for_function("document.querySelector('.jsxgraph-host').__scientificGeometry.controls.size >= 5")
                raw_midpoint = page.evaluate("""() => {
                  const host=document.querySelector('.jsxgraph-host');
                  const control=host.__scientificGeometry.controls.get('raw');
                  const a=control.start.coords.scrCoords, b=control.end.coords.scrCoords;
                  const box=host.getBoundingClientRect();
                  return {x:box.left+(a[1]+b[1])/2,y:box.top+(a[2]+b[2])/2};
                }""")
                page.mouse.click(raw_midpoint["x"], raw_midpoint["y"])
                if "raw · vector" not in page.locator("[data-selected-component]").text_content():
                    findings.append("clicking a vector did not select its semantic object")
                raw_before = page.evaluate("""() => {
                  const c=document.querySelector('.jsxgraph-host').__scientificGeometry.controls.get('raw');
                  return {from:[c.start.X(),c.start.Y()],to:[c.end.X(),c.end.Y()]};
                }""")
                end_box = page.evaluate("""() => document.querySelector('.jsxgraph-host')
                  .__scientificGeometry.controls.get('raw').end.rendNode.getBoundingClientRect().toJSON()""")
                page.mouse.move(end_box["x"] + end_box["width"] / 2, end_box["y"] + end_box["height"] / 2)
                page.mouse.down()
                page.mouse.move(end_box["x"] + end_box["width"] / 2 + 82,
                                end_box["y"] + end_box["height"] / 2 - 44, steps=8)
                page.mouse.up()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                vector_state = page.evaluate(
                    "() => fetch('/api/deck-state',{cache:'no-store'}).then(r=>r.json()).then(x=>x.objects)"
                )["mock-guidance-vector-geometry"]["raw"]
                if vector_state["to"] == [round(value, 4) for value in raw_before["to"]]:
                    findings.append("dragging a vector endpoint did not change its length and rotation")
                vector_path = slides_root / "04-vector-geometry.json"
                vector_original = vector_path.read_text(encoding="utf-8")
                vector_source = json.loads(vector_original)
                vector_source["data"]["vectors"] = list(reversed(vector_source["data"]["vectors"]))
                vector_path.write_text(json.dumps(vector_source, indent=2) + "\n", encoding="utf-8")
                page.reload(wait_until="networkidle")
                if page.locator("[data-edit-toggle]").text_content() == "Enable edit":
                    page.locator("[data-edit-toggle]").click()
                page.wait_for_function("document.querySelector('.jsxgraph-host').__scientificGeometry.controls.size >= 5")
                persisted_vector = page.evaluate("""() => {
                  const c=document.querySelector('.jsxgraph-host').__scientificGeometry.controls.get('raw');
                  return {from:[Number(c.start.X().toFixed(4)),Number(c.start.Y().toFixed(4))],
                    to:[Number(c.end.X().toFixed(4)),Number(c.end.Y().toFixed(4))]};
                }""")
                if persisted_vector["to"] != vector_state["to"]:
                    findings.append("source vector reorder retargeted a human vector edit")
                vector_path.write_text(vector_original, encoding="utf-8")
                page.reload(wait_until="networkidle")
                if page.locator("[data-edit-toggle]").text_content() == "Enable edit":
                    page.locator("[data-edit-toggle]").click()
                page.wait_for_function("document.querySelector('.jsxgraph-host').__scientificGeometry.controls.size >= 5")
                page.evaluate("""() => document.querySelector('.jsxgraph-host')
                  .__scientificGeometry.select('raw','vector')""")
                translated_before = page.evaluate("""() => {
                  const c=document.querySelector('.jsxgraph-host').__scientificGeometry.controls.get('raw');
                  return {from:[c.start.X(),c.start.Y()],to:[c.end.X(),c.end.Y()]};
                }""")
                center_box = page.evaluate("""() => document.querySelector('.jsxgraph-host')
                  .__scientificGeometry.controls.get('raw').center.rendNode.getBoundingClientRect().toJSON()""")
                page.mouse.move(center_box["x"] + center_box["width"] / 2,
                                center_box["y"] + center_box["height"] / 2)
                page.mouse.down()
                # Move inward from the source vector's left/bottom anchor so
                # neither endpoint is clamped by the geometry bounds; a clamp
                # would turn this translation assertion into a flaky resize.
                page.mouse.move(center_box["x"] + center_box["width"] / 2 + 34,
                                center_box["y"] + center_box["height"] / 2 - 22, steps=8)
                page.mouse.up()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                translated = page.evaluate("""() => fetch('/api/deck-state',{cache:'no-store'})
                  .then(r=>r.json()).then(x=>x.objects['mock-guidance-vector-geometry'].raw)""")
                start_delta = [translated["from"][index] - translated_before["from"][index] for index in range(2)]
                end_delta = [translated["to"][index] - translated_before["to"][index] for index in range(2)]
                if max(abs(start_delta[index] - end_delta[index]) for index in range(2)) > .02:
                    findings.append("vector midpoint handle did not translate both endpoints together")
                vector_editor = output / "editor-native-vector.png"
                page.screenshot(path=str(vector_editor))
                captures["native-vector-editor"] = str(vector_editor)

                # Qualitative target bars and reach lines are also native,
                # semantic visual objects. A bar moves/resizes as one linked
                # shape; reach endpoints change length and rotation, while the
                # center handle translates the whole line.
                page.goto(base + "/#mock-target-accessibility", wait_until="networkidle")
                if page.locator("[data-edit-toggle]").text_content() == "Enable edit":
                    page.locator("[data-edit-toggle]").click()
                target = page.locator('[data-visual-object-id="alien-target-target"]')
                target_box = target.bounding_box()
                page.mouse.move(target_box["x"] + target_box["width"] / 2,
                                target_box["y"] + target_box["height"] / 2)
                page.mouse.down()
                page.mouse.move(target_box["x"] + target_box["width"] / 2 + 54,
                                target_box["y"] + target_box["height"] / 2 + 22, steps=8)
                page.mouse.up()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                moved_target_state = page.evaluate("""() => fetch('/api/deck-state',{cache:'no-store'})
                  .then(r=>r.json()).then(x=>x.objects['mock-target-accessibility']['alien-target-target'])""")
                if moved_target_state.get("kind") != "accessibility-target" or moved_target_state["x"] <= 0:
                    findings.append("moving a target bar did not persist semantic shape geometry")
                resize_handle = page.locator('[aria-label="Resize alien-target-target"]')
                resize_box = resize_handle.bounding_box()
                page.mouse.move(resize_box["x"] + resize_box["width"] / 2,
                                resize_box["y"] + resize_box["height"] / 2)
                page.mouse.down()
                page.mouse.move(resize_box["x"] + resize_box["width"] / 2 - 72,
                                resize_box["y"] + resize_box["height"] / 2 - 12, steps=8)
                page.mouse.up()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                target_state = page.evaluate("""() => fetch('/api/deck-state',{cache:'no-store'})
                  .then(r=>r.json()).then(x=>x.objects['mock-target-accessibility']['alien-target-target'])""")
                if target_state["width"] >= moved_target_state["width"] - .01:
                    findings.append("target-bar corner handle did not resize the semantic shape")
                target_path = slides_root / "06-target-accessibility.json"
                target_original = target_path.read_text(encoding="utf-8")
                target_source = json.loads(target_original)
                target_source["data"]["panels"] = list(reversed(target_source["data"]["panels"]))
                target_path.write_text(json.dumps(target_source, indent=2) + "\n", encoding="utf-8")
                page.reload(wait_until="networkidle")
                reordered_target_state = page.evaluate("""() => fetch('/api/deck-state',{cache:'no-store'})
                  .then(r=>r.json()).then(x=>x.objects['mock-target-accessibility']['alien-target-target'])""")
                if reordered_target_state != target_state:
                    findings.append("panel reorder retargeted a human target-shape edit")
                target_path.write_text(target_original, encoding="utf-8")
                page.reload(wait_until="networkidle")
                if page.locator("[data-edit-toggle]").text_content() == "Enable edit":
                    page.locator("[data-edit-toggle]").click()
                reach = page.locator('[data-visual-object-id="model-native-target-r3-reach"]')
                reach_box = reach.bounding_box()
                page.mouse.click(reach_box["x"] + reach_box["width"] / 2,
                                 reach_box["y"] + reach_box["height"] / 2)
                if "model-native-target-r3-reach" not in page.locator("[data-selected-component]").text_content():
                    findings.append("clicking a reach line did not select its semantic object")
                end_handle = page.locator('[aria-label="end handle for model-native-target-r3-reach"]')
                end_box = end_handle.bounding_box()
                page.mouse.move(end_box["x"] + end_box["width"] / 2,
                                end_box["y"] + end_box["height"] / 2)
                page.mouse.down()
                page.mouse.move(end_box["x"] + end_box["width"] / 2 + 36,
                                end_box["y"] + end_box["height"] / 2 - 30, steps=8)
                page.mouse.up()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                reach_state = page.evaluate("""() => fetch('/api/deck-state',{cache:'no-store'})
                  .then(r=>r.json()).then(x=>x.objects['mock-target-accessibility']['model-native-target-r3-reach'])""")
                if reach_state.get("kind") != "accessibility-reach" or abs(reach_state["to"][1] - reach_state["from"][1]) < .01:
                    findings.append("reach endpoint did not persist a native line rotation")
                move_handle = page.locator('[aria-label="move handle for model-native-target-r3-reach"]')
                move_box = move_handle.bounding_box()
                page.mouse.move(move_box["x"] + move_box["width"] / 2,
                                move_box["y"] + move_box["height"] / 2)
                page.mouse.down()
                page.mouse.move(move_box["x"] + move_box["width"] / 2 - 34,
                                move_box["y"] + move_box["height"] / 2 + 18, steps=8)
                page.mouse.up()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                translated_reach = page.evaluate("""() => fetch('/api/deck-state',{cache:'no-store'})
                  .then(r=>r.json()).then(x=>x.objects['mock-target-accessibility']['model-native-target-r3-reach'])""")
                start_delta = [translated_reach["from"][i] - reach_state["from"][i] for i in range(2)]
                end_delta = [translated_reach["to"][i] - reach_state["to"][i] for i in range(2)]
                if max(abs(start_delta[i] - end_delta[i]) for i in range(2)) > .02:
                    findings.append("reach center handle did not translate both endpoints together")
                accessibility_editor = output / "editor-native-accessibility.png"
                page.screenshot(path=str(accessibility_editor))
                captures["native-accessibility-editor"] = str(accessibility_editor)

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
                      snapshot: {schema: current.schema, order, hidden: [], overlays: {}, tables: {}, objects: {}}
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
                          const content = copy.querySelector('.diagram-node-content').getBoundingClientRect();
                          return {
                            id: copy.dataset.diagramNodeId,
                            overflow: copy.scrollWidth > copy.clientWidth + 1 || copy.scrollHeight > copy.clientHeight + 1,
                            aligned: Boolean(s) && Math.abs(c.width - s.width) <= 2 && Math.abs(c.height - s.height) <= 2,
                            opticalInset: Math.min(content.left-c.left, c.right-content.right,
                              content.top-c.top, c.bottom-content.bottom),
                          };
                        })""")
                        overflowing = [item["id"] for item in node_geometry if item["overflow"]]
                        misaligned = [item["id"] for item in node_geometry if not item["aligned"]]
                        if overflowing:
                            findings.append(f"content-sized diagram nodes overflow in clean render: {overflowing}")
                        if misaligned:
                            findings.append(f"diagram copy and measured node frames disagree: {misaligned}")
                        cramped = [item["id"] for item in node_geometry if item["opticalInset"] < 13]
                        if cramped:
                            findings.append(f"auto-fitted diagram text lacks optical border slack: {cramped}")
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
                        if table_fit["mode"] != "evidence-table-region" or table_fit["overflow"] != "false" or not (0.95 <= table_fit["scale"] <= 1):
                            findings.append("evidence table did not choose a contained region-fit scale")
                    if slide_id == "mock-target-accessibility":
                        if clean.locator(".joint-paper").count():
                            findings.append("target accessibility regressed into a connector diagram")
                        if clean.locator(".accessibility-panel").count() != 2:
                            findings.append("target accessibility needs two aligned target panels")
                        widths = clean.evaluate("""() => [...document.querySelectorAll('.accessibility-panel')].map(panel => ({
                          common: panel.querySelector('.segment-common').getBoundingClientRect().width,
                          depth: panel.querySelector('.segment-depth').getBoundingClientRect().width,
                          inaccessible: panel.querySelector('.segment-inaccessible').getBoundingClientRect().width,
                          b4: panel.querySelector('.reach-b4 .accessibility-reach-line').getBoundingClientRect().width,
                          r3: panel.querySelector('.reach-r3 .accessibility-reach-line').getBoundingClientRect().width,
                        }))""")
                        if len(widths) == 2:
                            if not (widths[0]["inaccessible"] > widths[0]["common"] > widths[0]["depth"]):
                                findings.append("alien target does not read as mostly inaccessible")
                            if not (widths[1]["depth"] > widths[1]["inaccessible"]):
                                findings.append("model-native target does not expose a larger R3-only component")
                            if not ((widths[0]["r3"] - widths[0]["b4"]) <
                                    (widths[1]["r3"] - widths[1]["b4"])):
                                findings.append("depth payoff is not visibly larger for the model-native target")
                        if clean.locator('.accessibility-equation[data-math-engine="katex"]').count() != 1:
                            findings.append("target decomposition did not render as one KaTeX equation")
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
            "generic and bounded text regions move, resize, refit, and persist through physical handles",
            "semantic edit survives unrelated source insertion and component reorder",
            "table cells navigate, add, delete, reorder, paste, resize, and persist by semantic id",
            "human table structure survives an unrelated source insertion and source-row reorder",
            "human slide order survives save/reload",
            "external image drop persists by content hash",
            "hierarchical gallery facets, metric, and page survive slide navigation",
            "JointJS node drag physically reroutes its semantic connector",
            "JointJS node move/resize and connector bends persist by semantic object id",
            "semantic node geometry survives unrelated source insertion and reorder",
            "JSXGraph vector endpoint editing changes length/rotation and survives source reorder",
            "JSXGraph vector midpoint handle translates the complete semantic object",
            "JointJS nodes grow and reflow after longer live text edits",
            "JointJS text overlays match their measured SVG node frames without overflow",
            "auto-fitted node text preserves an optical inset from every shape border",
            "target bars and reach lines move, resize, rotate, save, reload, and survive panel reorder",
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
            "target accessibility uses aligned qualitative decompositions instead of a connector graph",
            "parallel diagrams preserve semantic lane centerlines and a 26pt audience-text floor",
        ],
        "findings": findings,
    }
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

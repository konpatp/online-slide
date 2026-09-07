#!/usr/bin/env python3
"""Real two-editor/two-contributor acceptance; all writes use a scratch deck."""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server import make_server
from playwright.sync_api import sync_playwright


def main():
    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        shutil.copytree(ROOT / "slides", root / "slides")
        http = make_server(ROOT / "public", root / "slides",
                           ROOT / "data/seed-state.json", root / "state.json")
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{http.server_address[1]}"
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                a = browser.new_page(viewport={"width": 1920, "height": 1080})
                b = browser.new_page(viewport={"width": 1920, "height": 1080})
                for page, slide in ((a, "mock-growth-trajectories"), (b, "mock-angle-evidence")):
                    page.goto(url + "/#" + slide, wait_until="networkidle")
                    page.locator("[data-edit-toggle]").click()
                a.locator('[data-component-id="headline"]').fill("Human A retained")
                a.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                initial = json.loads((root / "state.json").read_text())["order"]
                for name in ("contributor-a", "contributor-b"):
                    spec = json.loads((root / "slides/01-hero-plot.json").read_text())
                    spec.update(id=name, placement={"after": "mock-growth-trajectories"})
                    (root / "slides" / (name + ".json")).write_text(json.dumps(spec))
                b.locator('[data-component-id="headline"]').fill("Human B retained")
                b.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                b.locator(".thumb").first.locator('[data-action="move"][data-delta="1"]').click()
                b.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                for page in (a, b):
                    page.reload(wait_until="networkidle")
                state = json.loads((root / "state.json").read_text())
                assert state["overlays"]["mock-growth-trajectories"]["headline"]["text"] == "Human A retained"
                assert state["overlays"]["mock-angle-evidence"]["headline"]["text"] == "Human B retained"
                assert {"contributor-a", "contributor-b"} <= set(state["order"])
                assert state["order"][0] != initial[0]
                assert b.locator('[data-component-id="headline"]').text_content() == "Human B retained"
                # Same target: never silently overwrite. Preserve a recoverable
                # local draft while presenting the accepted server state.
                for page in (a, b):
                    page.goto(url + "/#mock-growth-trajectories", wait_until="networkidle")
                    if not page.locator("[data-edit-toggle]").get_attribute("aria-pressed") == "true":
                        page.locator("[data-edit-toggle]").click()
                a.locator('[data-component-id="headline"]').fill("First wins explicitly")
                a.wait_for_function("document.querySelector('[data-save-state]').textContent === 'Saved'")
                b.locator('[data-component-id="headline"]').fill("Conflicting draft retained")
                b.wait_for_function("document.querySelector('[data-save-state]').textContent.includes('Conflict')")
                assert b.locator("[data-conflict-draft]").is_visible()
                assert "Conflicting draft retained" in b.evaluate(
                    "localStorage.getItem('slidekit-conflict-draft:' + location.pathname)")
                assert json.loads((root / "state.json").read_text())["overlays"][
                    "mock-growth-trajectories"]["headline"]["text"] == "First wins explicitly"
                browser.close()
        finally:
            http.shutdown()
            http.server_close()
            thread.join()
    print(json.dumps({"ok": True, "twoContributors": True, "twoPhysicalEditors": True,
                      "humanOrderPreserved": True, "sameTargetConflictRetained": True,
                      "elapsedSeconds": round(time.perf_counter() - started, 2)}))


if __name__ == "__main__":
    main()

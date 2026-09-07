#!/usr/bin/env python3
"""Read-only catalog, automatic discovery, real preview and source-download proof."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server import make_server
from playwright.sync_api import sync_playwright


def main():
    with tempfile.TemporaryDirectory(prefix="catalog-review-") as tmp:
        root = Path(tmp)
        shutil.copytree(ROOT / "slides", root / "slides")
        server = make_server(ROOT / "public", root / "slides", ROOT / "data/seed-state.json", root / "state.json")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={"width":1920,"height":1080})
                errors, writes = [], []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("request", lambda request: writes.append(request.url) if request.method != "GET" else None)
                url = f"http://127.0.0.1:{server.server_address[1]}/catalog.html"
                before = (root / "state.json").read_bytes()
                page.goto(url)
                page.wait_for_selector(".example")
                assert page.locator("section").count() == 6
                assert page.evaluate("JSON.stringify(Object.keys(createScientificSlideRecipes({})).sort()) === JSON.stringify(Object.keys(scientificRecipeGuides).sort())")
                count = page.locator(".example").count()
                assert page.locator("iframe").count() == 0
                page.locator(".preview button").first.click()
                frame = page.frame_locator("iframe").first
                frame.locator(".slide-canvas").wait_for()
                with page.expect_download() as download:
                    page.get_by_text("Download source", exact=True).first.click()
                source = json.loads(Path(download.value.path()).read_text())
                assert source["recipe"] in page.locator("section").evaluate_all("nodes => nodes.map(n=>n.id)")
                assert (root / "state.json").read_bytes() == before
                source["id"] = "mock-added-catalog-example"
                (root / "slides" / "added.json").write_text(json.dumps(source))
                page.reload()
                page.wait_for_function("count => document.querySelectorAll('.example').length === count", arg=count+1)
                assert not errors, errors
                assert not writes, writes
                output = ROOT / "artifacts/catalog"
                output.mkdir(parents=True, exist_ok=True)
                page.locator(".preview button").first.click()
                page.frame_locator("iframe").first.locator(".slide-canvas").wait_for()
                page.screenshot(path=str(output / "catalog.png"))
                print(json.dumps({"ok":True,"recipes":6,"examplesAfterAddition":count+1,"stateWrites":0,"sourceDownload":True,"preview":True}))
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    main()

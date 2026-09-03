# test-tier: every-time
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import server


ROOT = Path(__file__).resolve().parents[1]


class ServerProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.state_path = root / "state.json"
        self.uploads_path = root / "uploads"
        self.http = server.make_server(
            ROOT / "public", ROOT / "slides", ROOT / "data" / "seed-state.json",
            self.state_path, self.uploads_path,
        )
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.http.server_address
        self.base = f"http://{host}:{port}"

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def get(self, path):
        with urlopen(self.base + path, timeout=2) as response:
            content_type = response.headers.get("Content-Type", "")
            body = response.read()
            if "json" in content_type:
                body = json.loads(body)
            return response.status, body

    def get_response(self, path):
        return urlopen(self.base + path, timeout=2)

    def post(self, path, value, content_type="application/json"):
        raw = json.dumps(value).encode() if content_type == "application/json" else value
        request = Request(self.base + path, data=raw, headers={"Content-Type": content_type}, method="POST")
        with urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read())

    @staticmethod
    def mutable_snapshot(state):
        return {key: json.loads(json.dumps(state[key])) for key in ("schema", "order", "hidden", "overlays")}

    def test_static_page_catalog_and_state_are_available(self):
        status, state = self.get("/api/deck-state")
        self.assertEqual(status, 200)
        self.assertEqual(state["schema"], "online-slide/state@2")
        self.assertEqual(len(state["order"]), 5)
        self.assertEqual(set(state["slides"]), set(state["order"]))
        self.assertEqual(len(state["sourceRevision"]), 64)
        status, health = self.get("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(health["catalog"]["recipes"]["hero-plot"], 1)
        with urlopen(self.base + "/", timeout=2) as response:
            page = response.read()
            self.assertIn(b"ScientificSlideKit", page)
            self.assertNotIn(b"__ASSET_REVISION__", page)
            self.assertEqual(response.headers["Cache-Control"], "no-cache, must-revalidate")
            self.assertRegex(page.decode(), r"geometry-runtime\.js\?v=[0-9a-f]{16}")
        with self.get_response("/geometry-runtime.js?v=1234") as response:
            self.assertEqual(response.headers["Cache-Control"], "public, max-age=31536000, immutable")
        with self.get_response("/geometry-runtime.js") as response:
            self.assertEqual(response.headers["Cache-Control"], "no-cache, must-revalidate")

    def test_revision_checked_semantic_overlay_save(self):
        _, state = self.get("/api/deck-state")
        changed = self.mutable_snapshot(state)
        changed["order"] = list(reversed(changed["order"]))
        changed["overlays"] = {
            "mock-growth-trajectories": {
                "headline": {
                    "text": "Edited through a semantic overlay",
                    "fontScale": 0.9,
                    "region": {"x": 80, "y": 24, "width": 1380, "height": 140},
                }
            }
        }
        status, saved = self.post("/api/deck-state", {
            "baseRevision": state["revision"], "baseSourceRevision": state["sourceRevision"],
            "snapshot": changed,
        })
        self.assertEqual(status, 200)
        self.assertEqual(saved["revision"], state["revision"] + 1)
        self.assertEqual(saved["order"], changed["order"])
        self.assertEqual(saved["overlays"], changed["overlays"])
        durable = json.loads(self.state_path.read_text())
        self.assertNotIn("slides", durable)
        self.assertEqual(durable["overlays"], changed["overlays"])

        with self.assertRaises(HTTPError) as conflict:
            self.post("/api/deck-state", {
                "baseRevision": state["revision"], "baseSourceRevision": state["sourceRevision"],
                "snapshot": changed,
            })
        self.assertEqual(conflict.exception.code, 409)

    def test_invalid_or_non_text_region_is_rejected(self):
        _, state = self.get("/api/deck-state")
        changed = self.mutable_snapshot(state)
        changed["overlays"] = {
            "mock-growth-trajectories": {
                "headline": {"region": {"x": 0, "y": 0, "width": 10, "height": 80}}
            }
        }
        with self.assertRaises(HTTPError) as error:
            self.post("/api/deck-state", {
                "baseRevision": state["revision"],
                "baseSourceRevision": state["sourceRevision"],
                "snapshot": changed,
            })
        self.assertEqual(error.exception.code, 400)
        self.assertIn("region overlay is invalid", json.loads(error.exception.read())["error"])

    def test_unknown_component_cannot_be_saved(self):
        _, state = self.get("/api/deck-state")
        changed = self.mutable_snapshot(state)
        changed["overlays"] = {"mock-growth-trajectories": {"block-3": {"text": "wrong"}}}
        with self.assertRaises(HTTPError) as error:
            self.post("/api/deck-state", {
                "baseRevision": state["revision"], "baseSourceRevision": state["sourceRevision"],
                "snapshot": changed,
            })
        self.assertEqual(error.exception.code, 400)
        self.assertIn("overlay target disappeared", json.loads(error.exception.read())["error"])

    def test_asset_upload_is_content_addressed_and_immutable(self):
        image = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4"/></svg>'
        status, receipt = self.post("/api/assets", image, "image/svg+xml")
        self.assertEqual(status, 201)
        self.assertRegex(receipt["src"], r"^uploads/[0-9a-f]{64}\.svg$")
        stored = self.uploads_path / receipt["src"].split("/", 1)[1]
        self.assertEqual(stored.read_bytes(), image)
        status, served = self.get("/" + receipt["src"])
        self.assertEqual(status, 200)
        self.assertEqual(served, image)


if __name__ == "__main__":
    unittest.main()

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
        self.state_path = Path(self.temp.name) / "state.json"
        self.http = server.make_server(
            ROOT / "public", ROOT / "data" / "seed.json", self.state_path
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
            return response.status, json.loads(response.read())

    def post(self, path, value):
        request = Request(
            self.base + path,
            data=json.dumps(value).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read())

    def test_static_page_and_state_are_available(self):
        status, state = self.get("/api/deck-state")
        self.assertEqual(status, 200)
        self.assertEqual(state["schema"], server.SCHEMA)
        self.assertEqual(len(state["order"]), 6)
        with urlopen(self.base + "/", timeout=2) as response:
            self.assertIn(b"online-slide", response.read())

    def test_revision_checked_atomic_save(self):
        _, state = self.get("/api/deck-state")
        changed = json.loads(json.dumps(state))
        changed["order"] = list(reversed(changed["order"]))
        changed["slides"][changed["order"][0]]["title"] = "Edited in the demo"
        status, saved = self.post(
            "/api/deck-state", {"baseRevision": state["revision"], "snapshot": changed}
        )
        self.assertEqual(status, 200)
        self.assertEqual(saved["revision"], state["revision"] + 1)
        self.assertEqual(saved["order"], changed["order"])
        self.assertEqual(json.loads(self.state_path.read_text())["revision"], 1)

        with self.assertRaises(HTTPError) as conflict:
            self.post("/api/deck-state", {"baseRevision": 0, "snapshot": changed})
        self.assertEqual(conflict.exception.code, 409)
        payload = json.loads(conflict.exception.read())
        self.assertEqual(payload["state"]["revision"], 1)

    def test_unknown_slide_cannot_be_saved(self):
        _, state = self.get("/api/deck-state")
        bad = json.loads(json.dumps(state))
        bad["order"][0] = "not-published"
        with self.assertRaises(HTTPError) as error:
            self.post("/api/deck-state", {"baseRevision": 0, "snapshot": bad})
        self.assertEqual(error.exception.code, 400)


if __name__ == "__main__":
    unittest.main()

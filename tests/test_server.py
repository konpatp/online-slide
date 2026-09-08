# test-tier: every-time
import json
import gzip
import re
import tempfile
import threading
import shutil
import unittest
import uuid
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
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
        self.slides_path = root / "slides"
        shutil.copytree(ROOT / "slides", self.slides_path)
        self.http = server.make_server(
            ROOT / "public", self.slides_path, ROOT / "data" / "seed-state.json",
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
        return {key: json.loads(json.dumps(state[key]))
                for key in ("schema", "order", "hidden", "overlays", "tables", "objects")}

    def test_create_is_atomic_retry_safe_and_survives_redeployment(self):
        _, before = self.get('/api/deck-state')
        intent = {'requestId': str(uuid.uuid4()), 'template': 'section-divider', 'after': before['order'][1]}
        original_bytes = self.state_path.read_bytes()
        with patch('server.atomic_write_json', side_effect=OSError('disk unavailable')):
            with self.assertRaises(HTTPError) as error:
                self.post('/api/slides', intent)
            self.assertEqual(error.exception.code, 503)
        self.assertEqual(self.state_path.read_bytes(), original_bytes)
        self.assertEqual(self.get('/api/deck-state')[1]['order'], before['order'])
        status, created = self.post('/api/slides', intent)
        self.assertEqual(status, 201)
        sid = created['loadedSlides'][0]
        self.assertEqual(created['order'][2], sid)
        self.assertEqual([key for key in created['order'] if key != sid], before['order'])
        self.assertEqual(created['slides'][sid]['data'], {'centered': True})
        persisted = self.state_path.read_bytes()
        self.assertEqual(self.post('/api/slides', intent)[0], 200)
        self.assertEqual(self.state_path.read_bytes(), persisted)
        with self.assertRaises(HTTPError) as error:
            self.post('/api/slides', {**intent, 'template': 'evidence-table'})
        self.assertEqual(error.exception.code, 409)
        # A new server generation reads human source from the external store,
        # not the source package or first-boot seed.
        fresh = server.make_server(ROOT/'public', self.slides_path, ROOT/'data/seed-state.json', self.state_path)
        fresh.server_close()
        self.assertEqual(self.state_path.read_bytes(), persisted)
        # Moving a user source into the authored directory is never a silent takeover.
        (self.slides_path/'collision.json').write_text(json.dumps(created['slides'][sid]))
        with self.assertRaises(server.ContractError):
            server.make_server(ROOT/'public', self.slides_path, ROOT/'data/seed-state.json', self.state_path)

    def test_runtime_fence_rejects_stale_source_reads_and_edits(self):
        _, before = self.get('/api/deck-state')
        with self.get_response('/api/runtime') as reply:
            revision = reply.headers['X-Slidekit-Runtime']
            self.assertEqual(json.load(reply)['runtimeRevision'], revision)
        self.assertEqual(before['runtimeRevision'], revision)
        for method, path in [('GET', '/api/bootstrap'), ('POST', '/api/deck-state')]:
            request = Request(self.base + path, method=method,
                              data=b'{}' if method == 'POST' else None,
                              headers={'X-Slidekit-Runtime': 'previous-renderer'})
            with self.assertRaises(HTTPError) as caught:
                urlopen(request)
            self.assertEqual(caught.exception.code, 409)
            self.assertEqual(caught.exception.headers['X-Slidekit-Runtime'], revision)
        self.assertEqual(self.get('/api/deck-state')[1], before)
        with urlopen(Request(self.base + '/api/bootstrap',
                             headers={'X-Slidekit-Runtime': revision})) as reply:
            self.assertEqual(reply.status, 200)

    def test_concurrent_creation_preserves_existing_edits_and_stale_saves(self):
        _, base = self.get('/api/deck-state')
        sid = base['order'][0]
        snapshot = self.mutable_snapshot(base)
        snapshot['hidden'] = [sid]
        headline = base['slides'][sid]['headline']
        snapshot['overlays'][sid] = {headline: {'text': 'Retained human title'}}
        intents = [{'requestId': str(uuid.uuid4()), 'template': template, 'after': sid}
                   for template in ('evidence-table', 'mechanism-pipeline')]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda value: self.post('/api/slides', value), intents))
        ids = {payload['loadedSlides'][0] for _, payload in results}
        _, saved = self.post('/api/deck-state', {
            'baseRevision': base['revision'], 'baseSourceRevision': base['sourceRevision'],
            'baseSlideRevisions': base['slideRevisions'], 'baseSnapshot': self.mutable_snapshot(base),
            'snapshot': snapshot})
        self.assertTrue(ids <= set(saved['order']))
        self.assertEqual(saved['overlays'], snapshot['overlays'])
        self.assertEqual(saved['hidden'], [sid])
        self.assertEqual([key for key in saved['order'] if key not in ids], base['order'])
        source_bytes = json.loads(self.state_path.read_text())['createdSlides']
        forged = self.mutable_snapshot(saved)
        forged['createdSlides'] = {}
        self.post('/api/deck-state', {'baseRevision': saved['revision'], 'baseSourceRevision': saved['sourceRevision'], 'snapshot': forged})
        self.assertEqual(json.loads(self.state_path.read_text())['createdSlides'], source_bytes)

    def test_layout_catalog_is_valid_read_only_and_rejects_unknown_creation(self):
        before = self.state_path.read_bytes()
        _, layouts = self.get('/api/layouts')
        self.assertEqual(layouts[0]['id'], 'section-divider')
        self.assertEqual(len(layouts), 6)
        for item in layouts:
            server.make_starter(item['id'], 'new-slide', '2026-01-01T00:00:00Z')
        for intent in (
            {'requestId': str(uuid.uuid4()), 'template': 'unknown', 'after': self.get('/api/deck-state')[1]['order'][0]},
            {'requestId': 'not-a-uuid', 'template': 'section-divider', 'after': 'unknown'},
            {'requestId': str(uuid.uuid4()), 'template': 'section-divider', 'after': 'unknown'},
        ):
            with self.assertRaises(HTTPError):
                self.post('/api/slides', intent)
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_static_page_catalog_and_state_are_available(self):
        status, state = self.get("/api/deck-state")
        self.assertEqual(status, 200)
        self.assertEqual(state["schema"], "online-slide/state@4")
        self.assertEqual(len(state["order"]), 6)
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
            revision = re.search(r'app\.js\?v=([0-9a-f]{16})', page.decode()).group(1)
            self.assertNotIn('<script src="plotly', page.decode())
        with self.get_response("/geometry-runtime.js?v=1234") as response:
            self.assertEqual(response.headers["Cache-Control"], "no-cache, must-revalidate")
        with self.get_response("/geometry-runtime.js?v=" + revision) as response:
            self.assertEqual(response.headers["Cache-Control"], "public, max-age=31536000, immutable")
        with self.get_response("/geometry-runtime.js") as response:
            self.assertEqual(response.headers["Cache-Control"], "no-cache, must-revalidate")

    def test_first_slide_bootstrap_and_revision_bound_sources(self):
        _, full = self.get('/api/deck-state')
        sid = full['order'][1]
        _, boot = self.get('/api/bootstrap?slide=' + sid)
        self.assertEqual(boot['loadedSlides'], [sid])
        self.assertEqual(boot['slides'][sid], full['slides'][sid])
        self.assertEqual(boot['order'], full['order'])
        self.assertNotIn('data', boot['slides'][full['order'][0]])
        self.assertEqual(boot['overlays'], full['overlays'])
        path = '/api/slides/' + sid + '?revision=' + full['slideRevisions'][sid]
        self.assertEqual(self.get(path)[1], full['slides'][sid])
        with self.get_response(path) as response:
            self.assertIn('private', response.headers['Cache-Control'])
        with self.assertRaises(HTTPError) as error:
            self.get('/api/slides/' + sid + '?revision=stale')
        self.assertEqual(error.exception.code, 409)

    def test_compact_save_retains_exact_mutable_state_without_catalog(self):
        _, state = self.get('/api/deck-state')
        _, saved = self.post('/api/deck-state', {
            'baseRevision': state['revision'], 'baseSourceRevision': state['sourceRevision'],
            'snapshot': self.mutable_snapshot(state), 'compact': True,
        })
        self.assertNotIn('slides', saved)
        self.assertEqual(saved['slideRevisions'], state['slideRevisions'])
        self.assertEqual(self.mutable_snapshot(saved), self.mutable_snapshot(state))
        self.assertEqual(self.state_path.read_text().count('"revision"'), 1)

    def test_gzip_negotiation_and_conditional_cache_preserve_exact_bytes(self):
        path = '/app.js'
        with self.get_response(path) as response:
            original = response.read()
            plain_etag = response.headers['ETag']
        request = Request(self.base + path, headers={'Accept-Encoding': 'gzip'})
        with urlopen(request) as response:
            raw = response.read()
            etag = response.headers['ETag']
            self.assertEqual(gzip.decompress(raw), original)
            self.assertLess(len(raw), len(original) / 2)
            self.assertEqual(response.headers['Vary'], 'Accept-Encoding')
            self.assertNotEqual(plain_etag, etag)
        request = Request(self.base + path, headers={'Accept-Encoding': 'gzip', 'If-None-Match': etag})
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 304)
        request = Request(self.base + path, headers={'Accept-Encoding': 'gzip;q=0, *;q=1'})
        with urlopen(request) as response:
            self.assertIsNone(response.headers.get('Content-Encoding'))
            self.assertEqual(response.read(), original)
        request = Request(self.base + '/api/bootstrap', headers={'Accept-Encoding': 'gzip'})
        with urlopen(request) as response:
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            self.assertIn('loadedSlides', json.loads(gzip.decompress(response.read())))

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
        self.assertEqual(durable["tables"], {})
        self.assertEqual(durable["objects"], {})

    def test_semantic_visual_object_geometry_is_revision_checked(self):
        _, state = self.get("/api/deck-state")
        changed = self.mutable_snapshot(state)
        changed["objects"] = {
            "mock-vector-construction": {
                "teacher-node": {
                    "kind": "diagram-node", "x": .26, "y": .14,
                    "width": .22, "height": .18,
                },
                "teacher-to-target": {
                    "kind": "diagram-edge", "vertices": [[.51, .21], [.58, .21]],
                },
            },
            "mock-guidance-vector-geometry": {
                "raw": {"kind": "vector", "from": [0, 0], "to": [6.2, 2.7]},
            },
        }
        _, saved = self.post("/api/deck-state", {
            "baseRevision": state["revision"], "baseSourceRevision": state["sourceRevision"],
            "snapshot": changed,
        })
        self.assertEqual(saved["objects"], changed["objects"])
        self.assertEqual(json.loads(self.state_path.read_text())["objects"], changed["objects"])

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

    def test_invalid_table_structure_is_rejected_before_persistence(self):
        _, state = self.get("/api/deck-state")
        changed = self.mutable_snapshot(state)
        changed["tables"] = {
            "mock-angle-evidence": {
                "columns": [
                    {"id": "column-direction", "label": "column-direction", "width": 1.5},
                    {"id": "column-low", "label": "column-low", "width": 1},
                ],
                "rows": [{
                    "id": "row-random", "label": "row-random",
                    "cells": ["missing-cell"], "best": "missing-cell", "globalBest": None,
                }],
                "components": {},
            }
        }
        with self.assertRaises(HTTPError) as error:
            self.post("/api/deck-state", {
                "baseRevision": state["revision"],
                "baseSourceRevision": state["sourceRevision"],
                "snapshot": changed,
            })
        self.assertEqual(error.exception.code, 400)
        self.assertIn("table cell disappeared", json.loads(error.exception.read())["error"])

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

    def test_png_upload_serves_webp_and_retains_original(self):
        import io
        from PIL import Image
        source = io.BytesIO()
        Image.new("RGB", (16, 16), "orange").save(source, format="PNG")
        original = source.getvalue()
        status, receipt = self.post("/api/assets", original, "image/png")
        self.assertEqual(status, 201)
        self.assertTrue(receipt["src"].endswith(".webp"))
        status, served = self.get("/" + receipt["src"])
        self.assertEqual(Image.open(io.BytesIO(served)).format, "WEBP")
        originals = list((self.uploads_path / "originals").glob("*.png"))
        self.assertEqual(len(originals), 1)
        self.assertEqual(originals[0].read_bytes(), original)

    def merge_save(self, base, snapshot):
        return self.post("/api/deck-state", {
            "baseRevision": base["revision"],
            "baseSourceRevision": base["sourceRevision"],
            "baseSlideRevisions": base["slideRevisions"],
            "baseSnapshot": self.mutable_snapshot(base),
            "snapshot": snapshot,
        })[1]

    def test_two_contributors_and_human_reorder_do_not_lose_edits(self):
        _, base = self.get("/api/deck-state")
        first = self.mutable_snapshot(base)
        first["overlays"] = {"mock-growth-trajectories": {"headline": {"text": "Human A"}}}
        self.merge_save(base, first)
        # Independent source contributions arrive while another editor retains
        # an older catalog and order. Neither contributor edits a registry.
        for name in ("contribution-a", "contribution-b"):
            spec = json.loads(json.dumps(base["slides"]["mock-growth-trajectories"]))
            spec["id"] = name
            spec["placement"] = {"after": "mock-growth-trajectories"}
            (self.slides_path / (name + ".json")).write_text(json.dumps(spec))
        second = self.mutable_snapshot(base)
        second["order"] = list(reversed(second["order"]))
        second["hidden"] = ["mock-angle-evidence"]
        second["overlays"] = {"mock-angle-evidence": {"headline": {"text": "Human B"}}}
        saved = self.merge_save(base, second)
        self.assertEqual([key for key in saved["order"] if key in base["order"]],
                         second["order"])
        self.assertIn("contribution-a", saved["order"])
        self.assertIn("contribution-b", saved["order"])
        self.assertEqual(saved["overlays"]["mock-growth-trajectories"]["headline"]["text"], "Human A")
        self.assertEqual(saved["overlays"]["mock-angle-evidence"]["headline"]["text"], "Human B")
        self.assertEqual(saved["hidden"], second["hidden"])
        self.assertEqual(json.loads(self.state_path.read_text())["overlays"], saved["overlays"])

    def test_same_target_conflict_is_explicit_and_atomic(self):
        _, base = self.get("/api/deck-state")
        first = self.mutable_snapshot(base)
        first["overlays"] = {"mock-growth-trajectories": {"headline": {"text": "First"}}}
        self.merge_save(base, first)
        before = self.state_path.read_bytes()
        second = self.mutable_snapshot(base)
        second["overlays"] = {"mock-growth-trajectories": {"headline": {"text": "Second"}}}
        with self.assertRaises(HTTPError) as error:
            self.merge_save(base, second)
        self.assertEqual(error.exception.code, 409)
        self.assertIn("headline/text", json.loads(error.exception.read())["error"])
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_bold_and_concurrent_wording_are_one_conflict_domain(self):
        _, base = self.get('/api/deck-state')
        sid, key = 'mock-angle-evidence', 'random-mid'
        original = base['slides'][sid]['components'][key]['text']
        wording = self.mutable_snapshot(base)
        wording['overlays'] = {sid:{key:{'text':'changed'}}}
        self.merge_save(base,wording)
        before = self.state_path.read_bytes()
        bold = self.mutable_snapshot(base)
        bold['overlays'] = {sid:{key:{'text':original,'marks':[{'start':0,'end':2,'bold':True}]}}}
        with self.assertRaises(HTTPError) as error:
            self.merge_save(base,bold)
        self.assertEqual(error.exception.code,409)
        self.assertEqual(self.state_path.read_bytes(),before)

    def test_source_change_on_edited_slide_fails_closed(self):
        _, base = self.get("/api/deck-state")
        path = self.slides_path / "01-hero-plot.json"
        spec = json.loads(path.read_text())
        spec["components"]["headline"]["text"] = "New source interpretation"
        path.write_text(json.dumps(spec))
        changed = self.mutable_snapshot(base)
        changed["overlays"] = {"mock-growth-trajectories": {"headline": {"text": "Old interpretation"}}}
        with self.assertRaises(HTTPError) as error:
            self.merge_save(base, changed)
        self.assertEqual(error.exception.code, 409)
        self.assertIn("source changed", json.loads(error.exception.read())["error"])

    def test_failed_write_does_not_advance_in_memory_revision(self):
        from unittest.mock import patch
        _, base = self.get("/api/deck-state")
        changed = self.mutable_snapshot(base)
        changed["hidden"] = ["mock-angle-evidence"]
        with patch.object(server, "atomic_write_json", side_effect=OSError("disk full")):
            with self.assertRaises(HTTPError):
                self.merge_save(base, changed)
        _, after = self.get("/api/deck-state")
        self.assertEqual(after["revision"], base["revision"])
        self.assertEqual(after["hidden"], base["hidden"])


if __name__ == "__main__":
    unittest.main()

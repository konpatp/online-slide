# test-tier: every-time
import copy
import json
import tempfile
import unittest
from pathlib import Path

from slidekit import ContractError, catalog_receipt, load_catalog, reconcile_state


ROOT = Path(__file__).resolve().parents[1]


class SlideKitContractTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog(ROOT / "slides")

    def initial_state(self):
        state, _ = reconcile_state({
            "schema": "online-slide/state@2", "revision": 0,
            "order": [], "hidden": [], "overlays": {}
        }, self.catalog)
        return state

    def test_four_recipes_and_semantic_components_are_complete(self):
        receipt = catalog_receipt(self.catalog)
        self.assertEqual(receipt["slides"], 4)
        self.assertEqual(set(receipt["recipes"].values()), {1})
        self.assertEqual(receipt["semanticComponentIds"], 73)
        self.assertEqual(receipt["positionalComponentIds"], 0)

    def test_human_order_and_edit_survive_unrelated_source_insertions(self):
        state = self.initial_state()
        state["order"] = ["mock-matched-gallery", "mock-growth-trajectories",
                          "mock-angle-evidence", "mock-vector-construction"]
        state["hidden"] = ["mock-angle-evidence"]
        state["overlays"] = {"mock-growth-trajectories": {"headline": {"text": "Human-authored headline"}}}
        changed_catalog = copy.deepcopy(self.catalog)
        plot = changed_catalog["mock-growth-trajectories"]
        plot["components"] = {
            "new-sibling": {"kind": "text", "text": "Unrelated source insertion", "role": "annotation"},
            **plot["components"],
        }
        reconciled, changed = reconcile_state(state, changed_catalog)
        self.assertFalse(changed)
        self.assertEqual(reconciled["order"], state["order"])
        self.assertEqual(reconciled["hidden"], state["hidden"])
        self.assertEqual(reconciled["overlays"], state["overlays"])

    def test_two_independent_contributors_need_no_shared_order_edit(self):
        with tempfile.TemporaryDirectory() as temp:
            slides = Path(temp)
            for path in (ROOT / "slides").glob("*.json"):
                (slides / path.name).write_bytes(path.read_bytes())
            base = load_catalog(slides)
            state = self.initial_state()
            state["order"] = list(reversed(state["order"]))
            template = json.loads((slides / "01-hero-plot.json").read_text())
            first = copy.deepcopy(template)
            first.update({"id": "contributor-alpha", "createdAt": "2026-09-01T09:00:00Z"})
            first["placement"] = {"after": "mock-growth-trajectories"}
            second = copy.deepcopy(template)
            second.update({"id": "contributor-beta", "createdAt": "2026-09-01T09:01:00Z"})
            second["placement"] = {"after": "mock-growth-trajectories"}
            (slides / "90-contributor-alpha.json").write_text(json.dumps(first))
            (slides / "91-contributor-beta.json").write_text(json.dumps(second))
            reconciled, changed = reconcile_state(state, load_catalog(slides))
            self.assertTrue(changed)
            anchor = reconciled["order"].index("mock-growth-trajectories")
            self.assertEqual(reconciled["order"][anchor + 1:anchor + 3], ["contributor-alpha", "contributor-beta"])
            existing = [item for item in reconciled["order"] if not item.startswith("contributor-")]
            self.assertEqual(existing, state["order"])

    def test_removed_edited_leaf_fails_closed(self):
        state = self.initial_state()
        state["overlays"] = {"mock-growth-trajectories": {"headline": {"text": "Keep me"}}}
        changed_catalog = copy.deepcopy(self.catalog)
        del changed_catalog["mock-growth-trajectories"]["components"]["headline"]
        with self.assertRaisesRegex(ContractError, "overlay target disappeared"):
            reconcile_state(state, changed_catalog)

    def test_removed_published_slide_fails_closed(self):
        state = self.initial_state()
        changed_catalog = dict(self.catalog)
        del changed_catalog["mock-angle-evidence"]
        with self.assertRaisesRegex(ContractError, "published slide source disappeared"):
            reconcile_state(state, changed_catalog)

    def test_initial_order_resolves_anchors_before_timestamps_and_rejects_cycles(self):
        catalog = copy.deepcopy(self.catalog)
        catalog["mock-matched-gallery"]["createdAt"] = "2026-01-01T00:00:00Z"
        state, _ = reconcile_state({
            "schema": "online-slide/state@2", "revision": 0,
            "order": [], "hidden": [], "overlays": {}
        }, catalog)
        self.assertEqual(state["order"], [
            "mock-growth-trajectories", "mock-angle-evidence",
            "mock-vector-construction", "mock-matched-gallery",
        ])
        catalog["mock-growth-trajectories"]["placement"] = {"after": "mock-matched-gallery"}
        with self.assertRaisesRegex(ContractError, "placement graph contains a cycle"):
            reconcile_state({
                "schema": "online-slide/state@2", "revision": 0,
                "order": [], "hidden": [], "overlays": {}
            }, catalog)


if __name__ == "__main__":
    unittest.main()

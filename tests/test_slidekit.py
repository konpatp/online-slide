# test-tier: every-time
import copy
import json
import tempfile
import unittest
from pathlib import Path

from slidekit import (
    ContractError,
    catalog_receipt,
    load_catalog,
    reconcile_state,
    validate_slide_spec,
)


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

    def test_five_recipes_and_semantic_components_are_complete(self):
        receipt = catalog_receipt(self.catalog)
        self.assertEqual(receipt["slides"], 5)
        self.assertEqual(set(receipt["recipes"].values()), {1})
        self.assertEqual(receipt["semanticComponentIds"], 109)
        self.assertEqual(receipt["positionalComponentIds"], 0)

    def test_vector_geometry_requires_latex_equations_and_bounded_labels(self):
        geometry = copy.deepcopy(self.catalog["mock-guidance-vector-geometry"])
        validate_slide_spec(geometry)
        geometry["components"]["equation-one"].pop("render")
        with self.assertRaisesRegex(ContractError, "must use LaTeX"):
            validate_slide_spec(geometry)
        geometry = copy.deepcopy(self.catalog["mock-guidance-vector-geometry"])
        geometry["data"]["labels"][0]["box"]["width"] = 101
        with self.assertRaisesRegex(ContractError, "bounded percentage box"):
            validate_slide_spec(geometry)
        geometry = copy.deepcopy(self.catalog["mock-guidance-vector-geometry"])
        geometry["data"]["labels"][0].pop("box")
        with self.assertRaisesRegex(ContractError, "bounded percentage box"):
            validate_slide_spec(geometry)

    def test_text_regions_are_explicit_bounded_semantic_geometry(self):
        slide = copy.deepcopy(self.catalog["mock-guidance-vector-geometry"])
        slide["components"]["remove-label"]["region"] = {
            "x": 40, "y": -20, "width": 540, "height": 96,
        }
        validate_slide_spec(slide)
        slide["components"]["remove-label"]["region"]["width"] = 12
        with self.assertRaisesRegex(ContractError, "invalid region"):
            validate_slide_spec(slide)

    def test_human_text_region_survives_an_unrelated_source_insertion(self):
        state = self.initial_state()
        region = {"x": 120, "y": 36, "width": 480, "height": 112}
        state["overlays"] = {
            "mock-guidance-vector-geometry": {"remove-label": {"region": region}}
        }
        changed_catalog = copy.deepcopy(self.catalog)
        geometry = changed_catalog["mock-guidance-vector-geometry"]
        geometry["components"] = {
            "unrelated-label": {"kind": "text", "text": "new sibling", "role": "annotation"},
            **geometry["components"],
        }
        reconciled, _ = reconcile_state(state, changed_catalog)
        self.assertEqual(
            reconciled["overlays"]["mock-guidance-vector-geometry"]["remove-label"]["region"],
            region,
        )

    def test_gallery_image_caption_is_an_independent_semantic_text_leaf(self):
        gallery = copy.deepcopy(self.catalog["mock-matched-gallery"])
        page_set = next(iter(gallery["data"]["pageSets"].values()))
        image_id = page_set[0]["rows"][0]["images"][2]
        gallery["components"]["sample-caption"] = {
            "kind": "text", "text": "class 12 · identity 03", "role": "image caption"
        }
        gallery["components"][image_id]["caption"] = "sample-caption"
        validate_slide_spec(gallery)
        gallery["components"][image_id]["caption"] = image_id
        with self.assertRaisesRegex(ContractError, "must reference text"):
            validate_slide_spec(gallery)

    def test_gallery_allows_only_a_partial_final_row(self):
        gallery = copy.deepcopy(self.catalog["mock-matched-gallery"])
        rows = next(iter(gallery["data"]["pageSets"].values()))[0]["rows"]
        rows[-1]["images"].pop()
        validate_slide_spec(gallery)
        rows[0]["images"].pop()
        with self.assertRaisesRegex(ContractError, "only the final gallery row may be partial"):
            validate_slide_spec(gallery)

    def test_mechanism_and_gallery_sources_are_semantic_not_positional(self):
        diagram = self.catalog["mock-vector-construction"]
        self.assertEqual(diagram["recipe"], "mechanism-pipeline")
        self.assertEqual({node["id"] for node in diagram["data"]["nodes"]}, {
            "query-node", "teacher-node", "student-node", "target-node",
            "prediction-node", "loss-node",
        })
        self.assertTrue(all("id" in edge for edge in diagram["data"]["edges"]))
        gallery = self.catalog["mock-matched-gallery"]
        self.assertEqual(gallery["recipe"], "hierarchical-gallery")
        selectors = gallery["data"]["selectors"]
        expected = 1
        for selector in selectors:
            expected *= len(selector["options"])
        self.assertEqual(len(gallery["data"]["views"]), expected)

    def test_mechanism_nodes_are_content_sized_unless_fixed_is_explicit(self):
        diagram = copy.deepcopy(self.catalog["mock-vector-construction"])
        validate_slide_spec(diagram)
        diagram["data"]["nodes"][0]["width"] = 240
        with self.assertRaisesRegex(ContractError, "dimensions require sizing=fixed"):
            validate_slide_spec(diagram)
        diagram["data"]["nodes"][0].update({"sizing": "fixed", "height": 112})
        validate_slide_spec(diagram)
        diagram["data"]["nodes"][0]["height"] = 0
        with self.assertRaisesRegex(ContractError, "positive width and height"):
            validate_slide_spec(diagram)

    def test_lane_layout_requires_semantic_lane_and_step_for_every_node(self):
        diagram = copy.deepcopy(self.catalog["mock-vector-construction"])
        self.assertEqual(diagram["data"]["layout"], "lanes")
        validate_slide_spec(diagram)
        del diagram["data"]["nodes"][0]["lane"]
        with self.assertRaisesRegex(ContractError, "needs numeric lane and step"):
            validate_slide_spec(diagram)

    def test_human_order_and_edit_survive_unrelated_source_insertions(self):
        state = self.initial_state()
        state["order"] = ["mock-matched-gallery", "mock-growth-trajectories",
                          "mock-angle-evidence", "mock-vector-construction",
                          "mock-guidance-vector-geometry"]
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
            "mock-vector-construction", "mock-guidance-vector-geometry",
            "mock-matched-gallery",
        ])
        catalog["mock-growth-trajectories"]["placement"] = {"after": "mock-matched-gallery"}
        with self.assertRaisesRegex(ContractError, "placement graph contains a cycle"):
            reconcile_state({
                "schema": "online-slide/state@2", "revision": 0,
                "order": [], "hidden": [], "overlays": {}
            }, catalog)


if __name__ == "__main__":
    unittest.main()

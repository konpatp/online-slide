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
    validate_state_snapshot,
    validate_slide_spec,
)


ROOT = Path(__file__).resolve().parents[1]


class SlideKitContractTests(unittest.TestCase):
    def test_index_routes_are_source_bound_and_unique(self):
        target=copy.deepcopy(next(iter(self.catalog.values())))
        index={'schema':'online-slide/slide@1','id':'contents-proof','recipe':'slide-index',
               'createdAt':'2026-09-06','headline':'headline','components':{
                   'headline':{'kind':'text','text':'Contents'},
                   'section':{'kind':'text','text':'Results'},
                   'entry':{'kind':'text','text':'One result'}},
               'data':{'sections':[{'heading':'section','items':[{'slide':target['id'],'label':'entry'}]}]}}
        validate_slide_spec(index)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'index.json').write_text(json.dumps(index))
            with self.assertRaisesRegex(ContractError,'index destination disappeared'):load_catalog(root)
            (root/'target.json').write_text(json.dumps(target))
            self.assertEqual(len(load_catalog(root)),2)
        index['data']['sections'][0]['items']*=2
        with self.assertRaisesRegex(ContractError,'duplicate index destination'):validate_slide_spec(index)

    def test_geometry_point_fill_and_coordinates_are_checked(self):
        spec=copy.deepcopy(self.catalog['mock-guidance-vector-geometry'])
        spec['data']['points']=[{'at':[0,0],'color':'#123456','fillColor':'#ffffff'}]
        validate_slide_spec(spec)
        spec['data']['points'][0]['fillColor']='invalid'
        with self.assertRaisesRegex(ContractError,'point fillColor'):validate_slide_spec(spec)
        spec['data']['points'][0]['fillColor']='#ffffff'
        spec['data']['points'][0]['at'][0]=float('nan')
        with self.assertRaisesRegex(ContractError,'finite coordinates'):validate_slide_spec(spec)

    def test_hero_equation_is_native_math_with_bounded_definition_count(self):
        spec={'schema':'online-slide/slide@1','id':'equation-proof','recipe':'hero-equation',
              'createdAt':'2026-09-06','headline':'headline','components':{
                  'headline':{'kind':'text','text':'One relation'},
                  'equation':{'kind':'text','text':'a+b=c','render':'latex'},
                  'definition':{'kind':'text','text':'A local decoder'}},
              'data':{'equation':'equation','definitions':['definition']}}
        validate_slide_spec(spec)
        spec['components']['equation'].pop('render')
        with self.assertRaises(ContractError):validate_slide_spec(spec)

    def test_hidden_component_is_retained_and_removal_fails_closed(self):
        state=self.initial_state()
        sid=next(iter(self.catalog));key=self.catalog[sid]['headline']
        state['overlays']={sid:{key:{'hidden':True}}}
        result,_=reconcile_state(state,self.catalog)
        self.assertTrue(result['overlays'][sid][key]['hidden'])
        state['overlays'][sid][key]['hidden']='yes'
        with self.assertRaises(ContractError):reconcile_state(state,self.catalog)

    def test_authored_table_widths_are_bounded_and_complete(self):
        spec = copy.deepcopy(next(s for s in load_catalog(ROOT / 'slides').values() if s['recipe']=='evidence-table'))
        spec['data']['columnWeights'] = [1]*len(spec['data']['columns'])
        validate_slide_spec(spec)
        for weights in ([1], [0]*len(spec['data']['columns']), [float('nan')]*len(spec['data']['columns'])):
            spec['data']['columnWeights'] = weights
            with self.assertRaises(ContractError):
                validate_slide_spec(spec)

    def setUp(self):
        self.catalog = load_catalog(ROOT / "slides")

    def initial_state(self):
        state, _ = reconcile_state({
            "schema": "online-slide/state@4", "revision": 0,
            "order": [], "hidden": [], "overlays": {}
        }, self.catalog)
        return state

    def test_six_recipes_and_semantic_components_are_complete(self):
        receipt = catalog_receipt(self.catalog)
        self.assertEqual(receipt["slides"], 6)
        self.assertEqual(set(value for value in receipt["recipes"].values() if value), {1})
        self.assertEqual(receipt["semanticComponentIds"], 126)
        self.assertEqual(receipt["positionalComponentIds"], 0)
        self.assertEqual(receipt["semanticVisualObjectIds"], 23)
        self.assertEqual(receipt["positionalVisualObjectIds"], 0)

    def test_state_v2_is_upgraded_but_an_old_client_cannot_erase_tables(self):
        upgraded, changed = reconcile_state({
            "schema": "online-slide/state@2", "revision": 7,
            "order": [], "hidden": [], "overlays": {},
        }, self.catalog)
        self.assertTrue(changed)
        self.assertEqual(upgraded["schema"], "online-slide/state@4")
        self.assertEqual(upgraded["tables"], {})
        self.assertEqual(upgraded["objects"], {})
        stale_client = dict(upgraded)
        stale_client["schema"] = "online-slide/state@2"
        with self.assertRaisesRegex(ContractError, "unsupported state schema"):
            validate_state_snapshot(stale_client, upgraded, self.catalog)

    def test_state_v3_is_upgraded_without_losing_table_state(self):
        prior = self.initial_state()
        prior["schema"] = "online-slide/state@3"
        prior.pop("objects")
        upgraded, changed = reconcile_state(prior, self.catalog)
        self.assertTrue(changed)
        self.assertEqual(upgraded["schema"], "online-slide/state@4")
        self.assertEqual(upgraded["objects"], {})

    def test_vector_geometry_requires_latex_equations_and_bounded_labels(self):
        geometry = copy.deepcopy(self.catalog["mock-guidance-vector-geometry"])
        validate_slide_spec(geometry)
        geometry["components"]["equation-one"].pop("render")
        with self.assertRaisesRegex(ContractError, "must use LaTeX"):
            validate_slide_spec(geometry)
        geometry = copy.deepcopy(self.catalog["mock-guidance-vector-geometry"])
        geometry["data"]["labels"][0]["box"]["width"] = 101
        with self.assertRaisesRegex(ContractError, "percentage label outside"):
            validate_slide_spec(geometry)
        geometry = copy.deepcopy(self.catalog["mock-guidance-vector-geometry"])
        geometry["data"]["labels"][0].pop("box")
        with self.assertRaisesRegex(ContractError, "finite bounded box"):
            validate_slide_spec(geometry)

    def test_world_text_regions_use_the_same_bounded_geometry_units(self):
        geometry=copy.deepcopy(self.catalog['mock-guidance-vector-geometry'])
        label=geometry['data']['labels'][0]
        label.update(space='world',box={'x':-1,'y':5,'width':2,'height':1})
        validate_slide_spec(geometry)
        label['box']['height']=20
        with self.assertRaisesRegex(ContractError,'world label outside'):validate_slide_spec(geometry)
        label['box']['height']=float('nan')
        with self.assertRaisesRegex(ContractError,'finite bounded box'):validate_slide_spec(geometry)

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

    def test_native_table_structure_uses_stable_row_column_and_cell_ids(self):
        state = self.initial_state()
        slide = self.catalog["mock-angle-evidence"]
        rows = slide["data"]["rows"]
        columns = slide["data"]["columns"]
        state["tables"] = {
            slide["id"]: {
                "columns": [
                    {"id": component_id, "label": component_id,
                     "width": 1.5 if index == 0 else 1}
                    for index, component_id in enumerate(columns)
                ],
                "rows": [
                    {
                        "id": row["label"], "label": row["label"],
                        "cells": list(row["cells"]),
                        "best": row["cells"][row["best"]],
                        "globalBest": row["cells"][row["globalBest"]]
                        if "globalBest" in row else None,
                    }
                    for row in reversed(rows)
                ],
                "components": {},
            }
        }
        # Row reorder never changes any saved cell identity.
        validated = validate_state_snapshot(state, state, self.catalog)
        self.assertEqual(
            validated["tables"][slide["id"]]["rows"][0]["cells"],
            rows[-1]["cells"],
        )

    def test_native_table_rejects_duplicate_ids_and_missing_cells(self):
        state = self.initial_state()
        slide = self.catalog["mock-angle-evidence"]
        state["tables"] = {
            slide["id"]: {
                "columns": [
                    {"id": component_id, "label": component_id, "width": 1}
                    for component_id in slide["data"]["columns"]
                ],
                "rows": [{
                    "id": row["label"], "label": row["label"],
                    "cells": list(row["cells"]),
                    "best": row["cells"][row["best"]], "globalBest": None,
                } for row in slide["data"]["rows"]],
                "components": {},
            }
        }
        state["tables"][slide["id"]]["rows"][1]["id"] = state["tables"][slide["id"]]["rows"][0]["id"]
        with self.assertRaisesRegex(ContractError, "duplicate table row id"):
            validate_state_snapshot(state, state, self.catalog)
        state = self.initial_state()
        state["tables"] = {
            slide["id"]: {
                "columns": [
                    {"id": component_id, "label": component_id, "width": 1}
                    for component_id in slide["data"]["columns"]
                ],
                "rows": [{
                    "id": "row-broken", "label": "row-random",
                    "cells": ["random-low", "missing-cell", "random-high", "random-best"],
                    "best": "random-low", "globalBest": None,
                }],
                "components": {},
            }
        }
        with self.assertRaisesRegex(ContractError, "table cell disappeared"):
            validate_state_snapshot(state, state, self.catalog)

    def test_native_table_rejects_unreferenced_inserted_components(self):
        state = self.initial_state()
        slide = self.catalog["mock-angle-evidence"]
        state["tables"] = {
            slide["id"]: {
                "columns": [
                    {"id": component_id, "label": component_id, "width": 1}
                    for component_id in slide["data"]["columns"]
                ],
                "rows": [{
                    "id": row["label"], "label": row["label"],
                    "cells": list(row["cells"]),
                    "best": row["cells"][row["best"]], "globalBest": None,
                } for row in slide["data"]["rows"]],
                "components": {
                    "retired-cell": {"kind": "text", "text": "stale", "role": "table-value"}
                },
            }
        }
        with self.assertRaisesRegex(ContractError, "unreferenced"):
            validate_state_snapshot(state, state, self.catalog)

    def test_target_accessibility_is_a_two_panel_latex_decomposition(self):
        slide = self.catalog["mock-target-accessibility"]
        self.assertEqual(slide["recipe"], "target-accessibility")
        self.assertEqual(len(slide["data"]["panels"]), 2)
        self.assertEqual(slide["components"][slide["data"]["equation"]]["render"], "latex")
        receipt = catalog_receipt(self.catalog)
        self.assertEqual(receipt["visualObjects"]["accessibility-target"], 2)
        self.assertEqual(receipt["visualObjects"]["accessibility-reach"], 4)

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

    def test_visual_geometry_survives_source_sibling_insertion_and_reorder(self):
        state = self.initial_state()
        state["objects"] = {
            "mock-vector-construction": {
                "teacher-node": {
                    "kind": "diagram-node", "x": .31, "y": .12,
                    "width": .18, "height": .22,
                }
            },
            "mock-guidance-vector-geometry": {
                "raw": {"kind": "vector", "from": [.2, .1], "to": [6.1, 2.8]}
            },
            "mock-target-accessibility": {
                "alien-target-target": {
                    "kind": "accessibility-target", "x": .12, "y": .31,
                    "width": .72, "height": .12,
                },
                "alien-target-r3-reach": {
                    "kind": "accessibility-reach", "from": [.22, .79], "to": [.71, .74],
                },
            },
        }
        changed_catalog = copy.deepcopy(self.catalog)
        diagram = changed_catalog["mock-vector-construction"]
        diagram["data"]["nodes"].insert(0, {
            "id": "review-node", "label": "query-label", "tone": "quiet", "lane": 0, "step": 4,
        })
        diagram["data"]["nodes"] = list(reversed(diagram["data"]["nodes"]))
        geometry = changed_catalog["mock-guidance-vector-geometry"]
        geometry["data"]["vectors"] = list(reversed(geometry["data"]["vectors"]))
        accessibility = changed_catalog["mock-target-accessibility"]
        accessibility["data"]["panels"] = list(reversed(accessibility["data"]["panels"]))
        reconciled, _ = reconcile_state(state, changed_catalog)
        self.assertEqual(reconciled["objects"], state["objects"])

    def test_visual_geometry_fails_closed_on_removed_or_changed_identity(self):
        state = self.initial_state()
        state["objects"] = {
            "mock-vector-construction": {
                "teacher-node": {
                    "kind": "diagram-node", "x": .31, "y": .12,
                    "width": .18, "height": .22,
                }
            }
        }
        changed_catalog = copy.deepcopy(self.catalog)
        changed_catalog["mock-vector-construction"]["data"]["nodes"] = [
            node for node in changed_catalog["mock-vector-construction"]["data"]["nodes"]
            if node["id"] != "teacher-node"
        ]
        changed_catalog["mock-vector-construction"]["data"]["edges"] = [
            edge for edge in changed_catalog["mock-vector-construction"]["data"]["edges"]
            if edge["from"] != "teacher-node" and edge["to"] != "teacher-node"
        ]
        with self.assertRaisesRegex(ContractError, "visual object target disappeared"):
            reconcile_state(state, changed_catalog)
        state["objects"]["mock-vector-construction"]["teacher-node"]["kind"] = "diagram-edge"
        with self.assertRaisesRegex(ContractError, "visual object kind changed"):
            reconcile_state(state, self.catalog)

    def test_vector_editability_requires_unique_semantic_object_ids(self):
        geometry = copy.deepcopy(self.catalog["mock-guidance-vector-geometry"])
        geometry["data"]["segments"][0]["id"] = geometry["data"]["vectors"][0]["id"]
        with self.assertRaisesRegex(ContractError, "duplicate visual object id"):
            validate_slide_spec(geometry)

    def test_human_order_and_edit_survive_unrelated_source_insertions(self):
        state = self.initial_state()
        state["order"] = ["mock-matched-gallery", "mock-growth-trajectories",
                          "mock-angle-evidence", "mock-vector-construction",
                          "mock-guidance-vector-geometry", "mock-target-accessibility"]
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

    def test_pending_table_does_not_require_an_invented_winner(self):
        spec = copy.deepcopy(self.catalog["mock-angle-evidence"])
        for row in spec["data"]["rows"]:
            row.pop("best", None)
        validate_slide_spec(spec)

    def test_gallery_view_keeps_matching_column_labels_and_initial_selection(self):
        spec = copy.deepcopy(self.catalog["mock-matched-gallery"])
        view = spec["data"]["views"][-1]
        view["columns"] = list(spec["data"]["columns"])
        spec["data"]["initialSelection"] = dict(view["selection"])
        validate_slide_spec(spec)
        view["columns"].pop()
        with self.assertRaisesRegex(ContractError, "matrix width"):
            validate_slide_spec(spec)

    def test_unknown_initial_gallery_selection_is_rejected(self):
        spec = copy.deepcopy(self.catalog["mock-matched-gallery"])
        spec["data"]["initialSelection"] = {"missing":"unavailable"}
        with self.assertRaisesRegex(ContractError,"initial gallery selection"):
            validate_slide_spec(spec)

    def test_initial_order_resolves_anchors_before_timestamps_and_rejects_cycles(self):
        catalog = copy.deepcopy(self.catalog)
        catalog["mock-matched-gallery"]["createdAt"] = "2026-01-01T00:00:00Z"
        state, _ = reconcile_state({
            "schema": "online-slide/state@3", "revision": 0,
            "order": [], "hidden": [], "overlays": {}
        }, catalog)
        self.assertEqual(state["order"], [
            "mock-growth-trajectories", "mock-angle-evidence",
            "mock-vector-construction", "mock-guidance-vector-geometry",
            "mock-matched-gallery", "mock-target-accessibility",
        ])
        catalog["mock-growth-trajectories"]["placement"] = {"after": "mock-matched-gallery"}
        with self.assertRaisesRegex(ContractError, "placement graph contains a cycle"):
            reconcile_state({
                "schema": "online-slide/state@3", "revision": 0,
                "order": [], "hidden": [], "overlays": {}
            }, catalog)


if __name__ == "__main__":
    unittest.main()

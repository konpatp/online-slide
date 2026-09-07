# test-tier: every-time
import copy
import unittest
import json
from pathlib import Path
import tempfile
from slidekit import ContractError, validate_slide_spec, validate_overlays, load_catalog


def slide():
    return {"schema":"online-slide/slide@1", "id":"mock-native-chart", "recipe":"chart-panels",
            "createdAt":"2026-09-06", "headline":"headline", "theme":{"accent":"#123456"},
            "components":{
                "headline":{"kind":"text","text":"Synthetic native curves"},
                "evidence":{"kind":"chart","figure":{
                    "data":[{"uid":"control","type":"scatter","x":[0,1],"y":[20,10]}],
                    "layout":{"yaxis":{"type":"log"},"annotations":[
                        {"name":"terminal","x":1,"y":10,"text":"Measured"}]}}}},
            "data":{"panels":[{"chart":"evidence"}]}}


class ChartPanelsTests(unittest.TestCase):
    def test_view_routes_are_unique_and_bind_real_selection(self):
        spec=slide()
        spec['components']['mode']={'kind':'text','text':'Mode'}
        spec['data']['selectors']=[{'id':'mode','label':'mode','options':[{'value':'first','label':'mode'}]}]
        spec['data']['views']=[{'selection':{'mode':'first'},'panels':[{'chart':'evidence'}]}]
        spec['routes']=[{'id':'old-chart::stage::0','selection':{'mode':'first'}}]
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'slide.json'
            path.write_text(json.dumps(spec));load_catalog(Path(root))
            spec['routes'][0]['selection']['mode']='missing'
            path.write_text(json.dumps(spec))
            with self.assertRaisesRegex(ContractError,'does not resolve'):load_catalog(Path(root))
            spec['routes'][0]['selection']['mode']='first'
            spec['routes'].append(copy.deepcopy(spec['routes'][0]))
            path.write_text(json.dumps(spec))
            with self.assertRaisesRegex(ContractError,'duplicate route'):load_catalog(Path(root))

    def test_retained_figure_requires_image_and_semantic_labels(self):
        spec=slide();spec['recipe']='evidence-figure'
        spec['components']['figure']={'kind':'image','src':'assets/synthetic.svg','alt':'Synthetic source figure'}
        spec['data']={'image':'figure','labels':['headline'],'caption':'headline'}
        validate_slide_spec(spec)
        spec['data']['image']='headline'
        with self.assertRaisesRegex(ContractError,'one image'):validate_slide_spec(spec)

    def test_source_native_values_and_log_axes_survive(self):
        spec = slide()
        before = copy.deepcopy(spec)
        validate_slide_spec(spec)
        self.assertEqual(spec, before)

    def test_annotation_edit_survives_sibling_insertion_and_reorder(self):
        spec = slide()
        overlay = {spec["id"]:{"evidence":{"chartLayout":{"annotations":{"terminal":{"text":"PI label"}}}}}}
        spec["components"]["evidence"]["figure"]["layout"]["annotations"].insert(0, {"name":"new-sibling","text":"New"})
        validate_slide_spec(spec)
        validate_overlays(overlay, {spec["id"]:spec})

    def test_removed_edited_annotation_fails_closed(self):
        spec = slide()
        overlay = {spec["id"]:{"evidence":{"chartLayout":{"annotations":{"removed":{"text":"PI label"}}}}}}
        with self.assertRaisesRegex(ContractError, "disappeared"):
            validate_overlays(overlay, {spec["id"]:spec})

    def test_duplicate_or_positional_annotation_identity_is_refused(self):
        spec = slide()
        annotation = spec["components"]["evidence"]["figure"]["layout"]["annotations"][0]
        annotation.pop("name")
        with self.assertRaisesRegex(ContractError,"authored names"):
            validate_slide_spec(spec)

    def test_data_edit_is_never_a_presentation_overlay(self):
        spec = slide()
        with self.assertRaisesRegex(ContractError,"unsupported chart edit"):
            validate_overlays({spec["id"]:{"evidence":{"chartLayout":{"data":[]}}}}, {spec["id"]:spec})

    def test_non_finite_evidence_is_rejected(self):
        spec = slide()
        spec["components"]["evidence"]["figure"]["data"][0]["y"][0] = float("nan")
        with self.assertRaisesRegex(ContractError, "non-finite"):
            validate_slide_spec(spec)

    def test_duplicate_annotation_identity_is_rejected(self):
        spec = slide()
        annotations = spec["components"]["evidence"]["figure"]["layout"]["annotations"]
        annotations.append(copy.deepcopy(annotations[0]))
        with self.assertRaisesRegex(ContractError, "authored names"):
            validate_slide_spec(spec)

    def test_facets_require_an_unambiguous_complete_matrix(self):
        spec = slide()
        spec["components"]["mode"] = {"kind":"text","text":"Mode"}
        spec["data"]["selectors"] = [{"id":"mode","label":"mode","options":[
            {"value":"first","label":"mode"},{"value":"second","label":"mode"}]}]
        spec["data"]["views"] = [{"selection":{"mode":"first"},"panels":[{"chart":"evidence"}]}]
        with self.assertRaisesRegex(ContractError,"incomplete"):
            validate_slide_spec(spec)
        spec["data"]["views"].append({"selection":{"mode":"second"},"panels":[{"chart":"evidence"}]})
        validate_slide_spec(spec)
        spec["data"]["views"].append(copy.deepcopy(spec["data"]["views"][0]))
        with self.assertRaisesRegex(ContractError,"ambiguous"):
            validate_slide_spec(spec)

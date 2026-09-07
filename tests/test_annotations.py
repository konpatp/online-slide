"""Native annotations use the same semantic state protocol on every recipe."""
# test-tier: every-time
import copy
import unittest
from pathlib import Path
from slidekit import ContractError,load_catalog,validate_slide_spec,validate_objects,catalog_receipt,validate_overlays

def fixture():
    spec=copy.deepcopy(load_catalog(Path(__file__).resolve().parents[1]/'slides')['mock-growth-trajectories'])
    spec['components']['human-note']={'kind':'text','text':'Up a bit.','region':{'x':1341,'y':704,'width':250,'height':80}}
    spec['annotations']=[
        {'kind':'rect','id':'human-highlight','color':'#ed3030','geometry':{'x':.6,'y':.4,'width':.19,'height':.1}},
        {'kind':'arrow','id':'human-pointer','color':'#ed3030','geometry':{'from':[.72,.65],'to':[.73,.54]}},
        {'kind':'text','component':'human-note'}]
    return spec

class AnnotationTests(unittest.TestCase):
    def test_chart_regions_are_bounded_without_mutating_evidence(self):
        spec=fixture();spec['components']['measured']={'kind':'chart','figure':{'data':[{'uid':'a','x':[1,2],'y':[3,4]}],'layout':{}}}
        region={'x':2,'y':30,'width':1200,'height':600}
        values=copy.deepcopy(spec['components']['measured']['figure'])
        validate_overlays({spec['id']:{'measured':{'region':region}}},{spec['id']:spec})
        self.assertEqual(spec['components']['measured']['figure'],values)
        region['width']=-1
        with self.assertRaisesRegex(ContractError,'region overlay is invalid'):
            validate_overlays({spec['id']:{'measured':{'region':region}}},{spec['id']:spec})

    def test_all_recipe_shapes_are_semantic_and_reorder_safe(self):
        spec=fixture();validate_slide_spec(spec)
        state={spec['id']:{'human-highlight':{'kind':'annotation-rect','x':.5,'y':.4,'width':.19,'height':.1}}}
        spec['annotations'].reverse();validate_objects(state,{spec['id']:spec})
        self.assertEqual(catalog_receipt({spec['id']:spec})['visualObjects']['annotation-rect'],1)
        spec['annotations']=[a for a in spec['annotations'] if a.get('id')!='human-highlight']
        with self.assertRaisesRegex(ContractError,'target disappeared'):validate_objects(state,{spec['id']:spec})

    def test_recipe_frame_is_revision_bound_geometry(self):
        spec=fixture();spec['frame']={'id':'evidence-frame','geometry':{'x':.05,'y':.2,'width':.9,'height':.65}}
        validate_slide_spec(spec)
        state={spec['id']:{'evidence-frame':{'kind':'recipe-frame',**spec['frame']['geometry']}}}
        validate_objects(state,{spec['id']:spec});spec.pop('frame')
        with self.assertRaisesRegex(ContractError,'target disappeared'):validate_objects(state,{spec['id']:spec})

    def test_duplicate_unbounded_and_malformed_annotations_fail(self):
        spec=fixture();spec['annotations'].append(copy.deepcopy(spec['annotations'][0]))
        with self.assertRaisesRegex(ContractError,'identity must be unique'):validate_slide_spec(spec)
        spec=fixture();spec['annotations'][0]['geometry']['x']=.99
        with self.assertRaisesRegex(ContractError,'outside its bounded plane'):validate_slide_spec(spec)
        spec=fixture();spec['components']['human-note'].pop('region')
        with self.assertRaisesRegex(ContractError,'bounded region'):validate_slide_spec(spec)

if __name__=='__main__':unittest.main()

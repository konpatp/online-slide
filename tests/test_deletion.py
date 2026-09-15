# test-tier: every-time
import copy
import unittest
from pathlib import Path
from slidekit import load_catalog, ContractError
from slidekit.overlays import validate_objects, validate_overlays, validate_text_boxes

class DeletionTests(unittest.TestCase):
    def setUp(self):
        self.catalog=load_catalog(Path(__file__).resolve().parents[1]/'slides')

    def test_tombstone_validates_identity_and_retains_geometry(self):
        slide=next(s for s in self.catalog.values() if s['recipe']=='mechanism-pipeline')
        sid=slide['id'];node=slide['data']['nodes'][0]['id']
        for value in ({'kind':'diagram-node','deleted':True},
                      {'kind':'diagram-node','deleted':True,'x':.1,'y':.1,'width':.2,'height':.2}):
            validate_objects({sid:{node:value}},self.catalog)
        for value in ({'kind':'diagram-node','deleted':'yes'}, {'kind':'segment','deleted':True},
                      {'kind':'diagram-node','deleted':True,'x':100}):
            with self.assertRaises(ContractError):validate_objects({sid:{node:value}},self.catalog)
        with self.assertRaises(ContractError):validate_objects({sid:{'removed-id':{'kind':'diagram-node','deleted':True}}},self.catalog)

    def test_component_deletion_is_boolean_and_source_bound(self):
        slide=next(iter(self.catalog.values()));sid=slide['id'];cid=slide['headline']
        validate_overlays({sid:{cid:{'deleted':True}}},self.catalog)
        with self.assertRaises(ContractError):validate_overlays({sid:{cid:{'deleted':'yes'}}},self.catalog)
        with self.assertRaises(ContractError):validate_overlays({sid:{'unknown':{'deleted':True}}},self.catalog)
        validate_text_boxes({sid:{'text-box-example':{'text':'note','region':{'x':0,'y':0,'width':100,'height':50},'deleted':True}}},self.catalog)

"""Curator text insertion reuses bounded text and atomic CAS persistence."""
# test-tier: every-time
import copy
import unittest
from pathlib import Path
from slidekit import (load_catalog, empty_state, reconcile_state, validate_state_snapshot,
                      merge_state_snapshot, source_revisions, ContractError, EditConflict)

class TextBoxTests(unittest.TestCase):
    def setUp(self):
        self.catalog=load_catalog(Path(__file__).resolve().parents[1]/'slides')
        self.base,_=reconcile_state(empty_state(),self.catalog)
        self.sid=self.base['order'][0]

    def insert(self,key='text-box-first'):
        state=copy.deepcopy(self.base)
        state['textBoxes']={self.sid:{key:{'text':'Readable text','region':{'x':100,'y':200,'width':520,'height':160}}}}
        return state

    def test_roundtrip_and_unrelated_insertions_merge(self):
        first=validate_state_snapshot(self.insert(),self.base,self.catalog)
        merged=merge_state_snapshot(self.base,self.insert('text-box-second'),first,self.catalog,source_revisions(self.catalog))
        self.assertEqual(len(merged['textBoxes'][self.sid]),2)
        restored,_=reconcile_state(merged,self.catalog)
        self.assertEqual(merged['textBoxes'],restored['textBoxes'])

    def test_same_box_conflicts_and_invalid_payloads_fail_closed(self):
        base=self.insert(); left=copy.deepcopy(base);right=copy.deepcopy(base)
        left['textBoxes'][self.sid]['text-box-first']['text']='Left'
        right['textBoxes'][self.sid]['text-box-first']['text']='Right'
        with self.assertRaises(EditConflict):
            merge_state_snapshot(base,left,right,self.catalog,source_revisions(self.catalog))
        for field,value in [('region',{'width':-1}),('html','<script>'),('marks',[{'start':0,'end':999,'bold':True}])]:
            bad=self.insert();bad['textBoxes'][self.sid]['text-box-first'][field]=value
            with self.subTest(field=field), self.assertRaises(ContractError):
                validate_state_snapshot(bad,self.base,self.catalog)

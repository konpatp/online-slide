# test-tier: every-time
import copy
import unittest
from pathlib import Path
from slidekit import ContractError, load_catalog, reconcile_state, validate_slide_spec

ROOT = Path(__file__).resolve().parents[1]


class TextMarksTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog(ROOT/'slides')
        self.sid = 'mock-angle-evidence'
        self.key = 'random-mid'
        self.state, _ = reconcile_state({'schema':'online-slide/state@4','revision':0,
                                        'order':[],'hidden':[],'overlays':{}}, self.catalog)

    def test_marks_survive_source_sibling_reordering(self):
        self.state['overlays'] = {self.sid:{self.key:{'text':'A bold value',
            'marks':[{'start':2,'end':6,'bold':True}]}}}
        changed = copy.deepcopy(self.catalog)
        changed[self.sid]['components'] = {'new-label':{'kind':'text','text':'Unrelated'},
                                          **dict(reversed(list(changed[self.sid]['components'].items())))}
        result, _ = reconcile_state(self.state, changed)
        self.assertEqual(result['overlays'], self.state['overlays'])

    def test_invalid_or_stale_ranges_fail_closed(self):
        for marks in ([{'start':0,'end':99,'bold':True}],
                      [{'start':True,'end':2,'bold':True}],
                      [{'start':0,'end':2,'bold':'yes'}],
                      [{'start':0,'end':2,'bold':True},{'start':1,'end':3,'bold':False}],
                      [{'start':0,'end':2,'bold':True,'html':'<script>'}]):
            with self.subTest(marks=marks), self.assertRaises(ContractError):
                self.state['overlays'] = {self.sid:{self.key:{'text':'12345','marks':marks}}}
                reconcile_state(self.state,self.catalog)

    def test_marks_without_their_text_are_rejected(self):
        self.state['overlays'] = {self.sid:{self.key:{'marks':[{'start':0,'end':2,'bold':True}]}}}
        with self.assertRaisesRegex(ContractError,'bind their exact text'):
            reconcile_state(self.state,self.catalog)

    def test_authored_unicode_and_math(self):
        spec = copy.deepcopy(self.catalog[self.sid])
        spec['components'][self.key].update(text='A😀B',marks=[{'start':1,'end':3,'bold':True}])
        validate_slide_spec(spec)
        spec['components'][self.key]['render'] = 'latex'
        with self.assertRaises(ContractError): validate_slide_spec(spec)

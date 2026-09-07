"""Independent native tables retain source and curator identities."""
# test-tier: every-time
import copy
import unittest
from slidekit import (ContractError, EditConflict, validate_slide_spec, validate_tables,
                      empty_state, reconcile_state, source_revisions, merge_state_snapshot)

def fixture():
    components={'headline':{'kind':'text','text':'Two independent comparisons'}}
    panels=[]
    for name in ('primary','secondary'):
        for key,value in [('heading',name),('visibility','Show '+name+' table'),('column','Model'),('value-column','Value'),('row','A'),('cell','12')]:
            components[name+'-'+key]={'kind':'text','text':value}
        panels.append({'id':name,'heading':name+'-heading','visibility':name+'-visibility',
                       'columns':[name+'-column',name+'-value-column'],
                       'rows':[{'label':name+'-row','cells':[name+'-cell']}]})
    return {'schema':'online-slide/slide@1','id':'two-tables','recipe':'evidence-table',
            'headline':'headline','createdAt':'2026-09-06','components':components,'data':{'tables':panels}}

def logical(panel):
    return {'columns':[{'id':key,'label':key,'width':1} for key in panel['columns']],
            'rows':[{'id':r['label'],'label':r['label'],'cells':r['cells'],'best':None,'globalBest':None} for r in panel['rows']],
            'components':{}}

class TablePanelTests(unittest.TestCase):
    def test_parallel_table_saves_merge_but_changed_source_refuses(self):
        spec=fixture();catalog={spec['id']:spec}
        base=reconcile_state(empty_state(),catalog)[0]
        current=copy.deepcopy(base);candidate=copy.deepcopy(base)
        current['tables']['two-tables::table::primary']=logical(spec['data']['tables'][0])
        candidate['tables']['two-tables::table::secondary']=logical(spec['data']['tables'][1])
        revisions=source_revisions(catalog)
        merged=merge_state_snapshot(base,candidate,current,catalog,revisions)
        self.assertEqual(set(merged['tables']),{'two-tables::table::primary','two-tables::table::secondary'})
        catalog=copy.deepcopy(catalog);catalog['two-tables']['components']['secondary-cell']['text']='Changed in source'
        with self.assertRaisesRegex(EditConflict,'source changed'):
            merge_state_snapshot(base,candidate,current,catalog,revisions)

    def test_independent_state_survives_source_panel_reorder(self):
        spec=fixture();validate_slide_spec(spec)
        state={'two-tables::table::secondary':logical(spec['data']['tables'][1])}
        spec['data']['tables'].reverse()
        validate_tables(state,{'two-tables':spec})
        self.assertEqual(state['two-tables::table::secondary']['rows'][0]['cells'],['secondary-cell'])

    def test_removed_or_renamed_edited_table_fails_closed(self):
        spec=fixture();state={'two-tables::table::secondary':logical(spec['data']['tables'][1])}
        spec['data']['tables'].pop()
        with self.assertRaisesRegex(ContractError,'table source disappeared'):
            validate_tables(state,{'two-tables':spec})

    def test_duplicate_identity_or_cross_table_cell_is_rejected(self):
        spec=fixture();spec['data']['tables'][1]['id']='primary'
        with self.assertRaisesRegex(ContractError,'unique semantic ids'):validate_slide_spec(spec)
        spec=fixture();spec['data']['tables'][1]['rows'][0]['cells']=['primary-cell']
        with self.assertRaisesRegex(ContractError,'share editable cells'):validate_slide_spec(spec)
        spec=fixture();state={'two-tables::table::secondary':logical(spec['data']['tables'][1])}
        state['two-tables::table::secondary']['rows'][0]['cells']=['primary-cell']
        with self.assertRaisesRegex(ContractError,'table cell disappeared'):validate_tables(state,{'two-tables':spec})

    def test_single_table_state_remains_compatible(self):
        spec=fixture();spec['data']=spec['data']['tables'][0]
        validate_slide_spec(spec);validate_tables({'two-tables':logical(spec['data'])},{'two-tables':spec})

if __name__=='__main__':unittest.main()

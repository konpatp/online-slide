"""Real pointer/save/reload proof for independently owned native tables."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
import server
from test_table_panels import fixture

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp);sources=root/'slides';shutil.copytree(ROOT/'slides',sources)
        spec=fixture();spec['components']['secondary-visibility']['hidden']=True
        path=sources/'99-two-tables.json';path.write_text(json.dumps(spec))
        index={'schema':'online-slide/slide@1','id':'index-proof','recipe':'slide-index','createdAt':'2026-09-06',
               'headline':'headline','components':{'headline':{'kind':'text','text':'Browse comparisons'},
               'section':{'kind':'text','text':'Evidence'},'tables':{'kind':'text','text':'Two comparisons'},
               'plot':{'kind':'text','text':'Measured trajectory'}},
               'data':{'sections':[{'heading':'section','items':[{'slide':'two-tables','label':'tables'},
                                                               {'slide':'mock-growth-trajectories','label':'plot'}]}]}}
        (sources/'98-index.json').write_text(json.dumps(index))
        http=server.make_server(ROOT/'public',sources,ROOT/'data/seed-state.json',root/'state.json',root/'uploads')
        thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True)
                page=browser.new_page(viewport={'width':1920,'height':1080})
                page.goto('http://%s:%s/#two-tables'%http.server_address,wait_until='networkidle')
                assert not page.locator('[data-table-panel-id="secondary"]').is_visible()
                page.locator('[data-edit-toggle]').click()
                cell=page.locator('[data-component-id="secondary-cell"]');cell.click();cell.fill('17')
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                assert page.locator('[data-component-id="primary-cell"]').text_content()=='12'
                page.locator('[data-table-action="row-add"]').click()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                assert page.locator('[data-table-panel-id="secondary"] tbody tr').count()==2
                assert page.locator('[data-table-panel-id="primary"] tbody tr').count()==1
                spec['data']['tables'].reverse();path.write_text(json.dumps(spec))
                page.reload(wait_until='networkidle')
                page.locator('[data-edit-toggle]').click()
                assert page.locator('[data-component-id="secondary-cell"]').text_content()=='17'
                assert page.locator('[data-table-panel-id="secondary"] tbody tr').count()==2
                control=page.locator('[data-component-id="secondary-visibility"]');control.click()
                page.locator('[data-hide-component]').click()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                page.reload(wait_until='networkidle')
                assert page.locator('[data-table-panel-id="secondary"]').is_visible()
                state=page.evaluate("fetch('api/deck-state').then(r=>r.json())")
                assert 'two-tables::table::secondary' in state['tables']
                assert 'two-tables::table::primary' not in state['tables']
                page.screenshot(path=str(args.output/'two-native-tables.png'))
                page.goto('http://%s:%s/#index-proof'%http.server_address,wait_until='networkidle')
                page.locator('a[href="#two-tables"]').click()
                page.wait_for_function("location.hash==='#two-tables'")
                page.goto('http://%s:%s/#index-proof'%http.server_address,wait_until='networkidle')
                page.locator('[data-edit-toggle]').click()
                page.locator('.slide-index-body header button').click()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                page.reload(wait_until='networkidle')
                hidden=page.evaluate("fetch('api/deck-state').then(r=>r.json()).then(s=>s.hidden)")
                assert 'two-tables' in hidden and 'mock-growth-trajectories' in hidden
                page.screenshot(path=str(args.output/'semantic-slide-index.png'))
                spec['components']['checkpoint-label']={'kind':'text','text':'Checkpoint'}
                spec['data']['tableSelector']={'label':'checkpoint-label','options':[
                    {'value':p['id'],'label':p['heading']} for p in spec['data']['tables']]}
                spec['data']['initialTable']='primary'
                path.write_text(json.dumps(spec))
                page.goto('http://%s:%s/?present=1#two-tables'%http.server_address,wait_until='networkidle')
                assert page.locator('[data-native-table]').count()==1
                assert page.locator('[data-table-panel-id="primary"]').is_visible()
                page.locator('.gallery-option-row button',has_text='secondary').click()
                assert page.locator('[data-native-table]').count()==1
                assert page.locator('[data-component-id="secondary-cell"]').text_content()=='17'
                page.reload(wait_until='networkidle')
                assert page.locator('[data-table-panel-id="secondary"]').is_visible()
                page.locator('.gallery-option-row button',has_text='primary').click()
                assert page.locator('[data-component-id="primary-cell"]').text_content()=='12'
                page.screenshot(path=str(args.output/'table-checkpoint-selector.png'))
                (args.output/'receipt.json').write_text(json.dumps({'ok':True,'findings':[],
                    'proofs':['real secondary-cell edit; primary unchanged','secondary row insertion remains table-local',
                              'source panel reorder preserves cell and structure','hidden table remains editable and show survives reload',
                              'index route clicks navigate; section visibility saves and survives reload',
                              'checkpoint buttons display exactly one table; selection and independent edits survive reload'],
                    'tableKeys':list(state['tables'])},indent=2)+'\n')
                browser.close()
        finally:http.shutdown();http.server_close()
    print('PASS: independent table pointer/save/reorder/visibility proof')

if __name__=='__main__':main()

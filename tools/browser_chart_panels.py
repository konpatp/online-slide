#!/usr/bin/env python3
"""Physical chart edit, persistence and source insertion proof in disposable state."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server import make_server
from playwright.sync_api import sync_playwright


def main():
    source = {"schema":"online-slide/slide@1","id":"mock-native-chart","recipe":"chart-panels",
              "createdAt":"2026-09-06","theme":{"accent":"#2a78d6"},"headline":"headline",
              "notes":"Synthetic source note: no research information.",
              "components":{"headline":{"kind":"text","text":"Native scientific chart editing"},
                "evidence":{"kind":"chart","figure":{"data":[
                  {"uid":"control","name":"Control","type":"scatter","x":[0,1,2],"y":[100,50,25]}],
                  "layout":{"xaxis":{"title":{"text":"Training epoch"}},
                    "yaxis":{"type":"log","title":{"text":"Synthetic error"}},
                    "annotations":[{"name":"terminal-result","text":"Measured endpoint", "x":1,"y":1.9,"showarrow":False}],
                    "margin":{"t":40,"b":100,"l":130,"r":60}}}}},
              "data":{"panels":[{"chart":"evidence"}]}}
    with tempfile.TemporaryDirectory(prefix="native-chart-proof-") as temporary:
        root=Path(temporary);slides=root/'slides';slides.mkdir()
        path=slides/'mock-native-chart.json';path.write_text(json.dumps(source))
        state_path=root/'state.json'
        def start():
            http=make_server(ROOT/'public',slides,root/'absent-seed.json',state_path)
            thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
            return http,thread,f"http://127.0.0.1:{http.server_address[1]}"
        http,thread,base=start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch()
                page=browser.new_page(viewport={"width":1920,"height":1080})
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base,wait_until='networkidle')
                page.locator('[data-edit-toggle]').click()
                page.wait_for_selector('[data-chart-ready="true"]')
                label=page.locator('.annotation-text').filter(has_text='Measured endpoint')
                box=label.bounding_box()
                page.mouse.click(box['x']+box['width']/2,box['y']+box['height']/2)
                page.keyboard.press('ControlOrMeta+A')
                page.keyboard.type('Curator endpoint')
                page.keyboard.press('Enter')
                page.wait_for_function("fetch('api/deck-state').then(r=>r.json()).then(s=>s.overlays['mock-native-chart']?.evidence?.chartLayout?.annotations?.['terminal-result']?.text === 'Curator endpoint')")
                before=json.loads(state_path.read_text())
                page.reload(wait_until='networkidle')
                page.wait_for_selector('[data-chart-ready="true"]')
                assert page.locator('.annotation-text').filter(has_text='Curator endpoint').count()==1
                page.locator('[data-notes-toggle]').click()
                assert 'Synthetic source note' in page.locator('[data-notes-dialog]').inner_text()
                page.keyboard.press('Escape')
                http.shutdown();http.server_close();thread.join()
                updated=copy.deepcopy(source)
                updated['components']['evidence']['figure']['layout']['annotations'].insert(0,
                    {"name":"unrelated-sibling","text":"Unrelated label","x":0,"y":1.5,"showarrow":False})
                path.write_text(json.dumps(updated))
                http,thread,base=start()
                page.goto(base,wait_until='networkidle')
                page.wait_for_selector('[data-chart-ready="true"]')
                assert page.locator('.annotation-text').filter(has_text='Curator endpoint').count()==1
                assert page.locator('.annotation-text').filter(has_text='Unrelated label').count()==1
                after=json.loads(state_path.read_text())
                assert before['overlays']==after['overlays']
                # The same compact facet controls used by galleries select
                # native chart variants and retain the choice across reloads.
                http.shutdown();http.server_close();thread.join()
                for key,label in [('facet','View'),('first','First'),('second','Second')]:
                    updated['components'][key]={'kind':'text','text':label}
                updated['components']['other-evidence']=copy.deepcopy(updated['components']['evidence'])
                updated['components']['other-evidence']['figure']['data'][0]['y'][0]=200
                updated['data']['selectors']=[{'id':'view','label':'facet','options':[
                    {'value':'first','label':'first'},{'value':'second','label':'second'}]}]
                updated['data']['views']=[
                    {'selection':{'view':'first'},'panels':[{'chart':'evidence'}]},
                    {'selection':{'view':'second'},'panels':[{'chart':'other-evidence'}]}]
                path.write_text(json.dumps(updated))
                http,thread,base=start()
                page.goto(base,wait_until='networkidle')
                page.get_by_role('button',name='Second',exact=True).click()
                page.wait_for_selector('[data-chart-id="other-evidence"][data-chart-ready="true"]')
                assert page.locator('.native-chart').evaluate('c=>c.data[0].y[0]')==200
                page.reload(wait_until='networkidle')
                page.wait_for_selector('[data-chart-id="other-evidence"][data-chart-ready="true"]')
                assert page.get_by_role('button',name='Second',exact=True).get_attribute('aria-pressed')=='true'
                page.get_by_role('button',name='First',exact=True).click()
                page.wait_for_selector('[data-chart-id="evidence"][data-chart-ready="true"]')
                assert page.locator('.annotation-text').filter(has_text='Curator endpoint').count()==1
                assert not errors, errors
                browser.close()
                print(json.dumps({"ok":True,"physicalClickTypeSaveReload":True,
                                  "semanticInsertionPreserved":True,"facetSelectionPersists":True,
                                  "notesAvailable":True,"liveWrites":0}))
        finally:
            http.shutdown();http.server_close();thread.join()


if __name__=='__main__':main()

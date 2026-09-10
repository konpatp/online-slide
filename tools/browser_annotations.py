"""Physical annotation gestures over a real plot; all writes are disposable."""
# browser-check: scratch-output
import argparse,json,shutil,sys,tempfile,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
import server
from test_annotations import fixture

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);sources=root/'slides';sources.mkdir()
        spec=fixture();spec['frame']={'id':'evidence-frame','geometry':{'x':.08,'y':.2,'width':.84,'height':.65}}
        path=sources/'plot.json';path.write_text(json.dumps(spec))
        seed=root/'seed.json';seed.write_text(json.dumps({'schema':'online-slide/state@4','revision':0,'order':[],'hidden':[],'overlays':{},'objects':{},'tables':{}}))
        http=server.make_server(ROOT/'public',sources,seed,root/'state.json',root/'uploads')
        threading.Thread(target=http.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1920,'height':1080})
                errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto('http://%s:%s/'%http.server_address,wait_until='networkidle')
                note=page.locator('[data-component-id="human-note"]')
                page.wait_for_function("(()=>{let e=document.querySelector('[data-component-id=human-note]');return e && e.getBoundingClientRect().height>0})()")
                assert note.is_visible(),(errors,note.evaluate('e=>({html:e.outerHTML,rect:e.getBoundingClientRect().toJSON()})'))
                page.locator('[data-edit-toggle]').click()
                move=page.get_by_role('button',name='Move layout frame',exact=True);box=move.bounding_box()
                page.mouse.move(box['x']+8,box['y']+8);page.mouse.down();page.mouse.move(box['x']+28,box['y']+28,steps=4);page.mouse.up()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                frame_before=page.evaluate("fetch('api/deck-state').then(r=>r.json()).then(s=>s.objects['mock-growth-trajectories']['evidence-frame'])")
                axis=page.locator('[data-component-id="'+spec['data']['xAxis']['label']+'"]');axis.click();axis.fill('Edited x axis')
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                assert frame_before==page.evaluate("fetch('api/deck-state').then(r=>r.json()).then(s=>s.objects['mock-growth-trajectories']['evidence-frame'])")
                rect=page.locator('[data-visual-object-id="human-highlight"]')
                box=rect.bounding_box();page.mouse.move(box['x']+4,box['y']+4);page.mouse.down();page.mouse.move(box['x']+64,box['y']+34,steps=5);page.mouse.up()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                resize=page.get_by_role('button',name='Resize human-highlight',exact=True)
                box=resize.bounding_box();page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2);page.mouse.down();page.mouse.move(box['x']+50,box['y']+35,steps=5);page.mouse.up()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                arrow=page.locator('[data-visual-object-id="human-pointer"]')
                box=arrow.bounding_box()
                page.mouse.click(box['x']+box['width']/2,box['y']+box['height']/2)
                handle=page.get_by_role('button',name='end handle for human-pointer',exact=True)
                box=handle.bounding_box();page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2);page.mouse.down();page.mouse.move(box['x']+40,box['y']-25,steps=5);page.mouse.up()
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                note.click();note.fill('Keep this annotation')
                page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'")
                before=page.evaluate("fetch('api/deck-state').then(r=>r.json())")
                assert before['objects'][spec['id']]['human-highlight']['x']>.6
                assert before['objects'][spec['id']]['human-highlight']['width']>.19
                assert before['objects'][spec['id']]['human-pointer']['to']!=[.73,.54]
                spec['annotations'].reverse();path.write_text(json.dumps(spec));page.reload(wait_until='networkidle')
                after=page.evaluate("fetch('api/deck-state').then(r=>r.json())")
                assert before['objects']==after['objects'] and before['overlays']==after['overlays']
                assert note.text_content()=='Keep this annotation'
                assert not errors,errors
                page.screenshot(path=str(args.output/'plot-annotations.png'))
                (args.output/'receipt.json').write_text(json.dumps({'ok':True,'errors':errors,'proofs':['physical rectangle move and resize','native text edit','semantic source reorder reload persistence','normal plot remains present']},indent=2))
                browser.close()
        finally:http.shutdown();http.server_close()
    print('PASS native annotations')

if __name__=='__main__':main()

"""Reproducible first-visible-slide and real save benchmark, disposable state only."""
import argparse,hashlib,importlib.util,json,sys,tempfile,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--site',type=Path,default=ROOT)
    p.add_argument('--engine',type=Path,default=ROOT,help='Server version being measured (defaults to this checkout)')
    p.add_argument('--state',type=Path)
    p.add_argument('--slide',action='append',required=True)
    p.add_argument('--runs',type=int,default=3)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    spec=importlib.util.spec_from_file_location('measured_server',args.engine/'server.py')
    server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)
    profile={'latency':200,'downloadThroughput':5_000_000/8,'uploadThroughput':2_000_000/8,'offline':False}
    rows=[]
    with tempfile.TemporaryDirectory(prefix='slide-latency-') as tmp:
        http=server.make_server(args.site/'public',args.site/'slides',args.state or args.site/'data/seed-state.json',Path(tmp)/'state.json')
        threading.Thread(target=http.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch()
                for sid in args.slide:
                    for run in range(args.runs):
                        context=browser.new_context(viewport={'width':1920,'height':1080})
                        page=context.new_page();cdp=context.new_cdp_session(page)
                        cdp.send('Network.enable');cdp.send('Network.emulateNetworkConditions',profile)
                        for mode in ('cold','warm'):
                            responses=[];errors=[]
                            def response(r):
                                if r.request.method=='POST':responses.append(r)
                            def page_error(error):errors.append(str(error))
                            page.on('response',response);page.on('pageerror',page_error)
                            start=time.perf_counter()
                            page.goto('http://%s:%s/?present=1#%s'%(*http.server_address,sid),wait_until='domcontentloaded')
                            page.wait_for_function("""id=>document.querySelector('.slide-canvas')?.dataset.slideId===id &&
                              document.querySelector('.slide-canvas .slide-title') &&
                              document.fonts.status==='loaded' &&
                              [...document.querySelectorAll('.slide-canvas img')].every(i=>i.complete && i.naturalWidth) &&
                              [...document.querySelectorAll('.native-chart')].every(c=>c.dataset.chartReady==='true')""",arg=sid,timeout=120000)
                            page.evaluate('()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
                            first=(time.perf_counter()-start)*1000
                            resources=page.evaluate('performance.getEntriesByType("resource").map(r=>({name:r.name.split("/").pop(),transfer:r.transferSize,duration:r.duration}))')
                            page.screenshot(path=str(args.output/f'{sid}-{run+1}-{mode}.png'))
                            page.keyboard.press('Escape')
                            page.locator('[data-edit-toggle]').click()
                            title=page.locator('.slide-title');original=title.text_content()
                            title.click();start_save=time.perf_counter();title.fill(original+' ')
                            page.wait_for_function("document.querySelector('[data-save-state]').textContent==='Saved'",timeout=120000)
                            save=(time.perf_counter()-start_save)*1000
                            row={'slide':sid,'run':run+1,'mode':mode,'firstVisibleMs':round(first), 'saveMs':round(save),
                              'saveResponseBytes':sum(len(r.body()) for r in responses),'resources':resources,'errors':errors}
                            assert responses,'benchmark did not perform a save'
                            assert not errors,errors
                            page.screenshot(path=str(args.output/f'{sid}-{run+1}-{mode}-edited.png'))
                            rows.append(row);print(json.dumps({k:v for k,v in row.items() if k!='resources'}),flush=True)
                            page.remove_listener('response',response)
                            page.remove_listener('pageerror',page_error)
                        context.close()
                browser.close()
        finally:http.shutdown();http.server_close()
    (args.output/'receipt.json').write_text(json.dumps({'profile':profile,'rows':rows,'liveWrites':0,
      'serverSHA256':hashlib.sha256((args.engine/'server.py').read_bytes()).hexdigest()},indent=2)+'\n')

if __name__=='__main__':main()

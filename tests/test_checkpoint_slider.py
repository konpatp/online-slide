"""Checkpoint control uses discrete options and keeps keyboard operation local."""
# test-tier: maintenance
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright

class CheckpointSliderTests(unittest.TestCase):
    def test_table_updates_before_pointer_release_without_replacing_slider(self):
        with sync_playwright() as p:
            browser=p.chromium.launch()
            page=browser.new_page()
            page.set_content('<main></main>')
            page.add_script_tag(path=str(Path(__file__).resolve().parents[1]/'public/recipes.js'))
            page.evaluate('''() => {
              const slide={id:'drag',components:{label:{text:'Epoch'}},data:{tables:[],tableSelector:{label:'label',options:[]}}};
              for(let i=0;i<5;i++) {
                slide.components['age'+i]={text:String(i)};
                slide.components['cell'+i]={text:String(100+i)};
                slide.data.tables.push({id:'t'+i,columns:['label','label'],rows:[{label:'label',cells:['cell'+i]}]});
                slide.data.tableSelector.options.push({value:'t'+i,label:'age'+i});
              }
              const recipes=window.createScientificSlideRecipes({
                editableText:(_,key)=>Object.assign(document.createElement('span'),{textContent:slide.components[key].text}),
                effectiveComponent:(_,key)=>slide.components[key],
                effectiveTable:s=>({columns:s.data.columns.map((label,i)=>({id:String(i),label,width:1})),rows:s.data.rows.map(r=>({...r,id:r.label}))}),
                startTableColumnResize:()=>{},fitGroupInRegion:()=>{}
              });
              recipes['evidence-table'](document.querySelector('main'),slide);
              window.originalSlider=document.querySelector('input');
            }''')
            slider=page.locator('input[type=range]');box=slider.bounding_box()
            page.mouse.move(box['x']+8,box['y']+box['height']/2)
            page.mouse.down()
            for fraction,index in [(0.5,2),(0.99,4),(0.25,1)]:
                page.mouse.move(box['x']+box['width']*fraction,box['y']+box['height']/2,steps=4)
                self.assertEqual(page.locator('[data-table-panel-id]').get_attribute('data-table-panel-id'),'t'+str(index))
                self.assertTrue(page.evaluate('originalSlider===document.querySelector("input")'))
            page.mouse.up()
            browser.close()

    def test_pointer_and_keyboard_select_exact_option(self):
        with sync_playwright() as p:
            browser=p.chromium.launch()
            page=browser.new_page()
            page.set_content('<main></main>')
            page.add_script_tag(path=str(Path(__file__).resolve().parents[1]/'public/recipes.js'))
            page.evaluate('''() => {
              const slide={id:'test',components:{label:{text:'Epoch'},a:{text:'2 epochs'},b:{text:'40 epochs'}}};
              window.createScientificSlideRecipes({editableText:(_,key)=>Object.assign(document.createElement('span'),{textContent:slide.components[key].text}),effectiveComponent:(_,key)=>slide.components[key]});
              window.changed=[];window.nav=0;document.addEventListener('keydown',()=>window.nav++);
              window.renderScientificFacetControls(document.querySelector('main'),slide,[{id:'age',label:'label',control:'slider',options:[{value:'early',label:'a'},{value:'late',label:'b'}]}],{age:'early'},(_,v)=>window.changed.push(v));
            }''')
            slider=page.locator('input[type=range]')
            slider.focus();slider.press('ArrowRight')
            self.assertEqual(page.evaluate('window.changed'),['late'])
            self.assertEqual(page.evaluate('window.nav'),0)
            self.assertEqual(slider.get_attribute('aria-valuetext'),'40 epochs')
            slider.fill('0');slider.dispatch_event('change')
            self.assertEqual(page.evaluate('window.changed')[-1],'early')
            browser.close()

"""Checkpoint control uses discrete options and keeps keyboard operation local."""
# test-tier: maintenance
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright

class CheckpointSliderTests(unittest.TestCase):
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

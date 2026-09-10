// Recipe owns layout; injected editor capabilities own mutable state.
export function createAnnotations(api) {
const global = window;
const {editableText,bindTextRegion,wireVisualObjects} = api;
function annotations(canvas,slide) {
  var records=[];
  if(slide.frame) {
    var body=canvas.querySelector(':scope > .recipe-body');
    if(body) records.push({id:slide.frame.id,kind:'recipe-frame',mode:'rect',article:canvas,element:body,
      source:Object.assign({kind:'recipe-frame'},slide.frame.geometry)});
  }
  (slide.annotations || []).forEach(function(item) {
    if(item.kind==='text') {
      var text=editableText(slide,item.component,'div','slide-annotation-text');
      canvas.appendChild(text);
      bindTextRegion(slide,item.component,text,text,{alwaysFit:true});
      return;
    }
    var element=document.createElement('div');
    element.className='slide-annotation-shape annotation-'+item.kind;
    element.style.setProperty('--annotation-color',item.color);
    element.style.setProperty('--annotation-width',(item.strokeWidth || 3)+'px');
    element.style.borderRadius=(item.cornerRadius || 0)+'px';
    canvas.appendChild(element);
    records.push({id:item.id,kind:item.kind==='rect'?'annotation-rect':'annotation-line',
      mode:item.kind==='rect'?'rect':'line',article:canvas,element:element,
      source:Object.assign({kind:item.kind==='rect'?'annotation-rect':'annotation-line'},item.geometry)});
  });
  wireVisualObjects(slide,records);
}


return annotations;
}

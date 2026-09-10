// Recipe owns layout; injected editor capabilities own mutable state.
export function createSlideIndex(api) {
const global = window;
const {editableText} = api;
function slideIndex(canvas,slide) {
  var body=document.createElement('div');body.className='recipe-body slide-index-body';
  function visibilityButton(ids) {
    var hidden=ids.every(api.isSlideHidden),button=document.createElement('button');
    button.type='button';button.className='index-visibility';button.textContent=hidden?'Show':'Hide';
    button.setAttribute('aria-label',(hidden?'Show ':'Hide ')+ids.join(', '));
    button.disabled=!api.isEditMode();
    button.addEventListener('click',function(event) {event.preventDefault();event.stopPropagation();api.setSlidesHidden(ids,!hidden);});
    return button;
  }
  slide.data.sections.forEach(function(section) {
    var group=document.createElement('section'),head=document.createElement('header');
    head.appendChild(editableText(slide,section.heading,'div','index-section-heading'));
    head.appendChild(visibilityButton(section.items.map(function(item) {return item.slide;})));
    group.appendChild(head);
    var links=document.createElement('div');links.className='index-links';
    section.items.slice().sort(function(a,b) {return api.orderOfSlide(a.slide)-api.orderOfSlide(b.slide);}).forEach(function(item) {
      var row=document.createElement('div');row.className='index-link-row';
      if(api.isSlideHidden(item.slide)) row.classList.add('index-destination-hidden');
      var link=document.createElement('a');link.href='#'+item.slide;
      link.appendChild(editableText(slide,item.label,'div','index-link-label'));
      link.addEventListener('click',function(event) {if(api.isEditMode())event.preventDefault();});
      row.appendChild(link);row.appendChild(visibilityButton([item.slide]));links.appendChild(row);
    });
    group.appendChild(links);body.appendChild(group);
  });
  canvas.appendChild(body);
}


return slideIndex;
}

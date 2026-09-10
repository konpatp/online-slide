import {scientificRecipeGuides} from './guides';
export {scientificRecipeGuides};
import {createHeroPlot} from './heroPlot';
import {createSlideIndex} from './slideIndex';
import {createEvidenceTable} from './evidenceTable';
import {createTargetAccessibility} from './targetAccessibility';
import {createWireVisualObjects} from './wireVisualObjects';
import {createAnnotations} from './annotations';
import {createMechanismPipeline} from './mechanismPipeline';
import {createVectorGeometry} from './vectorGeometry';
import {createHierarchicalGallery} from './hierarchicalGallery';

export function createScientificSlideRecipes(api) {
const global = window;
const {editableText,effectiveComponent,galleryImage,bindTextRegion} = api;
global.renderScientificFacetControls = function (host, slide, selectors, selection, onChange) {
  host.textContent = "";
  selectors.forEach(function (selector) {
    var group = document.createElement("div"); group.className = "gallery-selector";
    group.appendChild(editableText(slide, selector.label, "span", "gallery-selector-label"));
    var options = document.createElement("div"); options.className = "gallery-option-row";
    selector.options.forEach(function (option) {
      var button = document.createElement("button"); button.type = "button";
      button.textContent = effectiveComponent(slide, option.label).text;
      button.setAttribute("aria-pressed", String(selection[selector.id] === option.value));
      button.addEventListener("click", function (event) { event.stopPropagation(); onChange(selector.id, option.value); });
      options.appendChild(button);
    });
    group.appendChild(options); host.appendChild(group);
  });
};


  api = {...api, wireVisualObjects:createWireVisualObjects(api)};
  const heroPlot = createHeroPlot(api);
  const slideIndex = createSlideIndex(api);
  const evidenceTable = createEvidenceTable(api);
  const targetAccessibility = createTargetAccessibility(api);
  const annotations = createAnnotations(api);
  const mechanismPipeline = createMechanismPipeline(api);
  const vectorGeometry = createVectorGeometry(api);
  const hierarchicalGallery = createHierarchicalGallery(api);

return {
  "evidence-figure": function(canvas,slide) {
    var body=document.createElement('div');body.className='recipe-body evidence-figure-body';
    var labels=document.createElement('div');labels.className='evidence-figure-labels';
    (slide.data.labels||[]).forEach(function(key){labels.appendChild(editableText(slide,key,'div','evidence-figure-label'));});
    body.appendChild(labels);
    var frame=galleryImage(slide,slide.data.image);frame.classList.add('evidence-figure-frame');body.appendChild(frame);
    if(slide.data.caption)body.appendChild(editableText(slide,slide.data.caption,'div','evidence-figure-caption'));
    canvas.appendChild(body);
  },
  "hero-equation": function (canvas,slide) {
    var body=document.createElement('div');body.className='recipe-body hero-equation-body';
    if(slide.data.question) {
      body.classList.add('with-question');
      body.appendChild(editableText(slide,slide.data.question,'p','hero-equation-question'));
    }
    var frame=document.createElement('div');frame.className='hero-equation-frame';
    var equation=editableText(slide,slide.data.equation,'div','hero-equation-value');
    frame.appendChild(equation);body.appendChild(frame);
    bindTextRegion(slide,slide.data.equation,equation,frame,{alwaysFit:true,fitMode:'hero-equation',minSize:40});
    var definitions=document.createElement('div');definitions.className='hero-equation-definitions';
    slide.data.definitions.forEach(function(key){definitions.appendChild(editableText(slide,key,'div','hero-equation-definition'));});
    body.appendChild(definitions);canvas.appendChild(body);
  },
  "section-divider": function () {},
  annotations: annotations,
  "chart-panels": function (canvas, slide) { return global.renderScientificChartPanels(canvas, slide, api); },
  "hero-plot": heroPlot,
  "evidence-table": evidenceTable,
  "slide-index": slideIndex,
  "target-accessibility": targetAccessibility,
  "mechanism-pipeline": mechanismPipeline,
  "vector-geometry": vectorGeometry,
  "hierarchical-gallery": hierarchicalGallery
};

}

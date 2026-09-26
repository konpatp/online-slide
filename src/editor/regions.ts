import type {Region} from './model';
import {fitTextInRegion, registerTextFit} from './fit';
import {measureBox} from './transform';
import type {TransformLayer} from './transform';
import {roundBox} from './boxes';
import type {Box} from './boxes';
const CANONICAL_SLIDE_WIDTH = 1920, CANONICAL_SLIDE_HEIGHT = 1080;
interface RegionOptions {minSize?:number; fitMode?:string; alwaysFit?:boolean; fitRegistered?:boolean}
interface Binding {key:string; slideId:string; componentId:string; element:HTMLElement; host:HTMLElement; minSize:number; fitMode:string; alwaysFit:boolean; fitRegistered:boolean}
interface RegionHost {
  getComponent(slideId:string,componentId:string): {kind:string; region?:Region; deleted?:boolean} | null;
  transforms: TransformLayer;
  selectRegion(slideId:string,componentId:string,element:HTMLElement): void;
  updateOverlay(slideId:string,componentId:string,key:'region',value:Region): void;
  resizeChart(host:HTMLElement): void;
}
export function createTextRegions({getComponent,transforms,selectRegion,updateOverlay,resizeChart}:RegionHost) {
const textRegionBindings = new Map<string,Binding>();
function textRegionKey(slideId: string, componentId: string) {
  return slideId + "@" + componentId;
}

function bindTextRegion(slide: {id:string}, componentId:string, element:HTMLElement, host?:HTMLElement, options:RegionOptions = {}) {
  options = options || {};
  var key = textRegionKey(slide.id, componentId);
  var binding = {
    key: key,
    slideId: slide.id,
    componentId: componentId,
    element: element,
    host: host || element,
    minSize: options.minSize || 20,
    fitMode: options.fitMode || "editable-text-region",
    alwaysFit: options.alwaysFit === true,
    fitRegistered: options.fitRegistered === true
  };
  binding.host.classList.add("editable-text-region");
  binding.host.setAttribute("data-text-region-for", componentId);
  textRegionBindings.set(key, binding);
  requestAnimationFrame(function () {
    if (textRegionBindings.get(key) !== binding || !binding.host.isConnected) return;
    applyTextRegion(binding);
    registerRegion(binding);
  });
  return binding.host;
}

function canvasCoordinateScale(canvas: HTMLElement) {
  return {
    x: canvas.clientWidth / CANONICAL_SLIDE_WIDTH,
    y: canvas.clientHeight / CANONICAL_SLIDE_HEIGHT
  };
}

function ensureTextRegionFit(binding: Binding) {
  if (binding.fitRegistered) return;
  binding.fitRegistered = true;
  registerTextFit(binding.element, binding.host, {
    mode: binding.fitMode,
    minSize: binding.minSize
  });
}

function applyTextRegion(binding: Binding) {
  var canvas = binding.host.closest<HTMLElement>(".slide-canvas");
  if (!canvas) return;
  var component = getComponent(binding.slideId,binding.componentId);
  if (!component) return;
  binding.host.classList.toggle('curator-deleted', Boolean(component.deleted));
  var region = component.region;
  if (!region) {
    if (binding.alwaysFit) ensureTextRegionFit(binding);
    return;
  }
  var scale = canvasCoordinateScale(canvas);
  binding.host.style.translate = (region.x * scale.x).toFixed(2) + "px " +
    (region.y * scale.y).toFixed(2) + "px";
  binding.host.style.width = (region.width * scale.x).toFixed(2) + "px";
  binding.host.style.height = (region.height * scale.y).toFixed(2) + "px";
  binding.host.classList.add("text-region-bounded");
  if(component.kind==='chart') {
    binding.host.style.flex='none';
    resizeChart(binding.host);
    return;
  }
  ensureTextRegionFit(binding);
  fitTextInRegion(binding.element, binding.host, {
    mode: binding.fitMode,
    minSize: binding.minSize
  });
}

function applyAllTextRegions() {
  textRegionBindings.forEach(function (binding) {
    if (binding.host.isConnected) applyTextRegion(binding);
  });
}

/** Text and charts become shared transform targets. Table cells belong to
 * their table and diagram text to its node; neither moves on its own. */
function registerRegion(binding: Binding) {
  var canvas = binding.host.closest<HTMLElement>(".slide-canvas");
  var component = getComponent(binding.slideId, binding.componentId);
  if (!canvas || !component || !['text', 'chart'].includes(component.kind)) return;
  if (binding.host.closest('[data-table-cell], .diagram-node-copy')) return;
  var chart = component.kind === 'chart';
  transforms.register({
    key: binding.key, label: chart ? 'chart region' : 'text region',
    hits: [binding.host], canvas, group: 'region:' + binding.key,
    identity: {slideId: binding.slideId, componentId: binding.componentId},
    minWidth: 48, minHeight: 28,
    // Plot zoom, legend and annotation drags stay Plotly's; move by the border.
    nativeSelector: chart ? '.js-plotly-plot, .main-svg' : undefined,
    textAt: node => {
      var text = node.closest<HTMLElement>('.semantic-component');
      return text && binding.host.contains(text) ? text : null;
    },
    select: () => selectRegion(binding.slideId, binding.componentId, binding.element),
    edit: () => regionEdit(binding, canvas!)
  });
}

/** Regions store an offset from the object's flow position plus a size.
 * Convert absolute boxes to that form, correcting any flow shift a new width
 * causes so the object lands exactly where it was dragged. */
function regionEdit(binding: Binding, canvas: HTMLElement) {
  var measured = measureBox(binding.host, canvas);
  var current = getComponent(binding.slideId, binding.componentId)?.region;
  var region: Region = current ? Object.assign({}, current)
    : {x: 0, y: 0, width: measured.width, height: measured.height};
  var origin = {x: measured.x - region.x, y: measured.y - region.y};
  function write(next: Box) {
    var value = roundBox({x: next.x - origin.x, y: next.y - origin.y, width: next.width, height: next.height});
    updateOverlay(binding.slideId, binding.componentId, 'region', value);
    applyTextRegion(binding);
    return value;
  }
  return {
    update(next: Box) {
      var value = write(next);
      var landed = measureBox(binding.host, canvas);
      if (Math.abs(landed.x - next.x) > .5 || Math.abs(landed.y - next.y) > .5) {
        origin = {x: landed.x - value.x, y: landed.y - value.y};
        write(next);
      }
    }
  };
}

return {bindTextRegion,applyAllTextRegions,
  clearTextRegions() {textRegionBindings.clear();}};
}

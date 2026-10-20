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
  var host = binding.host;
  if (!region) {
    if (host.classList.contains("text-region-bounded")) {
      for (const name of ["translate", "width", "height", "margin-right", "margin-bottom", "flex", "display"]) host.style.removeProperty(name);
      host.classList.remove("text-region-bounded", "region-footprint");
    }
    if (binding.alwaysFit) ensureTextRegionFit(binding);
    return;
  }
  var scale = canvasCoordinateScale(canvas);
  host.style.translate = (region.x * scale.x).toFixed(2) + "px " +
    (region.y * scale.y).toFixed(2) + "px";
  host.style.width = (region.width * scale.x).toFixed(2) + "px";
  host.style.height = (region.height * scale.y).toFixed(2) + "px";
  reserveFootprint(host, region, scale);
  host.classList.add("text-region-bounded");
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

/** The object keeps occupying its footprint in the recipe's layout whatever
 * its edited size: margins absorb the difference, so a resize never reflows
 * a neighbour (flex rows, grids and stacks all lay out margin boxes). */
function reserveFootprint(host: HTMLElement, region: Region, scale: {x: number; y: number}) {
  for (const name of ["margin-right", "margin-bottom", "display"]) host.style.removeProperty(name);
  // Regions saved before footprints occupy their own size, drawn inline-block.
  host.classList.toggle("region-footprint", Boolean(region.footprint));
  if (!region.footprint) return;
  // Keep the element's own display so its layout box is its natural one;
  // only an inline element needs inline-block to take a size at all.
  var style = getComputedStyle(host);
  if (style.display === "inline") host.style.display = "inline-block";
  host.style.marginRight = (parseFloat(style.marginRight) + (region.footprint.width - region.width) * scale.x).toFixed(2) + "px";
  host.style.marginBottom = (parseFloat(style.marginBottom) + (region.footprint.height - region.height) * scale.y).toFixed(2) + "px";
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
 * causes so the object lands exactly where it was dragged. The first edit
 * fixes the footprint at the space the object occupies now (its natural box,
 * or the size an older region already occupies), so neighbours never move. */
function regionEdit(binding: Binding, canvas: HTMLElement) {
  var measured = measureBox(binding.host, canvas);
  var current = getComponent(binding.slideId, binding.componentId)?.region;
  var region: Region = current ? Object.assign({}, current)
    : {x: 0, y: 0, width: measured.width, height: measured.height};
  var exact = (value: number) => Math.round(value * 100) / 100; // sub-pixel: any error would reflow neighbours
  var footprint = region.footprint || (current ? {width: current.width, height: current.height}
    : {width: exact(measured.width), height: exact(measured.height)});
  var origin = {x: measured.x - region.x, y: measured.y - region.y};
  function write(next: Box) {
    var box = roundBox({x: next.x - origin.x, y: next.y - origin.y, width: next.width, height: next.height});
    var value: Region = {...box, footprint: {width: footprint.width, height: footprint.height}};
    if (!current && Math.abs(next.width - measured.width) < .05 && Math.abs(next.height - measured.height) < .05) {
      value.width = footprint.width; value.height = footprint.height; // untouched size stays exact
    }
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

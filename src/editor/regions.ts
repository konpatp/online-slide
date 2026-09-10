import type {Region} from './model';
import {fitTextInRegion, registerTextFit} from './fit';
const CANONICAL_SLIDE_WIDTH = 1920, CANONICAL_SLIDE_HEIGHT = 1080;
interface RegionOptions {minSize?:number; fitMode?:string; alwaysFit?:boolean; fitRegistered?:boolean}
interface Binding {key:string; slideId:string; componentId:string; element:HTMLElement; host:HTMLElement; minSize:number; fitMode:string; alwaysFit:boolean; fitRegistered:boolean}
interface Gesture {kind:'move'|'resize';binding:Binding;canvas:HTMLElement;canvasRect:DOMRect;hostRect:DOMRect;startX:number;startY:number;region:Region}
interface RegionHost {
  getComponent(slideId:string,componentId:string): {kind:string; region?:Region} | null;
  getSelected(): {slideId:string;componentId:string} | null;
  isEditMode(): boolean;
  beginChange(): void; persist(): void;
  updateOverlay(slideId:string,componentId:string,key:'region',value:Region): void;
  resizeChart(host:HTMLElement): void;
}
export function createTextRegions({getComponent,getSelected,isEditMode,beginChange,persist,updateOverlay,resizeChart}:RegionHost) {
const textRegionBindings = new Map<string,Binding>();
let textRegionFrame: HTMLElement | null = null;
let regionGesture: Gesture | null = null;
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
  });
  return binding.host;
}

function canvasCoordinateScale(canvas: HTMLElement) {
  return {
    x: canvas.clientWidth / CANONICAL_SLIDE_WIDTH,
    y: canvas.clientHeight / CANONICAL_SLIDE_HEIGHT
  };
}

function canvasRenderScale(canvas: HTMLElement) {
  var rect = canvas.getBoundingClientRect();
  return {
    x: rect.width / canvas.clientWidth,
    y: rect.height / canvas.clientHeight
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

function currentTextRegionBinding() {
  const selected = getSelected();
  if (!selected || !isEditMode()) return null;
  var component = getComponent(selected.slideId,selected.componentId);
  if (!component || !['text','chart'].includes(component.kind)) return null;
  return textRegionBindings.get(textRegionKey(selected.slideId, selected.componentId)) || null;
}

function removeTextRegionFrame() {
  if (textRegionFrame) textRegionFrame.remove();
  textRegionFrame = null;
}

function regionFromBinding(binding: Binding) {
  var canvas = binding.host.closest<HTMLElement>(".slide-canvas");
  if (!canvas) throw new Error("Detached text region");
  var scale = canvasRenderScale(canvas);
  var rect = binding.host.getBoundingClientRect();
  var component = getComponent(binding.slideId,binding.componentId);
  return component?.region ? Object.assign({}, component.region) : {
    x: 0,
    y: 0,
    width: rect.width / scale.x,
    height: rect.height / scale.y
  };
}

function syncTextRegionFrame() {
  var binding = currentTextRegionBinding();
  if (!binding || !binding.host.isConnected) {
    removeTextRegionFrame();
    return;
  }
  var canvas = binding.host.closest<HTMLElement>(".slide-canvas");
  if (!canvas) return;
  if (!textRegionFrame || textRegionFrame.parentElement !== canvas) {
    removeTextRegionFrame();
    textRegionFrame = document.createElement("div");
    textRegionFrame.className = "text-region-frame";
    textRegionFrame.setAttribute("data-text-region-frame", binding.componentId);
    var move = document.createElement("button");
    move.type = "button";
    move.className = "text-region-move-handle";
    move.setAttribute("aria-label", "Move text region");
    move.title = "Drag to move this text region";
    move.addEventListener("pointerdown", function (event) {
      startTextRegionGesture("move", event);
    });
    var resize = document.createElement("button");
    resize.type = "button";
    resize.className = "text-region-resize-handle";
    resize.setAttribute("aria-label", "Resize text region");
    resize.title = "Drag to resize; text wraps and fits inside";
    resize.addEventListener("pointerdown", function (event) {
      startTextRegionGesture("resize", event);
    });
    textRegionFrame.appendChild(move);
    textRegionFrame.appendChild(resize);
    canvas.appendChild(textRegionFrame);
  }
  textRegionFrame.setAttribute("data-text-region-frame", binding.componentId);
  var regionKind=getComponent(binding.slideId,binding.componentId)?.kind==='chart'?'chart':'text';
  textRegionFrame.querySelector('.text-region-move-handle')!.setAttribute('aria-label','Move '+regionKind+' region');
  textRegionFrame.querySelector('.text-region-resize-handle')!.setAttribute('aria-label','Resize '+regionKind+' region');
  if (!canvas) return;
  var canvasRect = canvas.getBoundingClientRect();
  var rect = binding.host.getBoundingClientRect();
  var scale = canvasRenderScale(canvas);
  textRegionFrame.style.left = ((rect.left - canvasRect.left) / scale.x) + "px";
  textRegionFrame.style.top = ((rect.top - canvasRect.top) / scale.y) + "px";
  textRegionFrame.style.width = (rect.width / scale.x) + "px";
  textRegionFrame.style.height = (rect.height / scale.y) + "px";
}

function startTextRegionGesture(kind: 'move' | 'resize', event: PointerEvent) {
  var binding = currentTextRegionBinding();
  if (!binding) return;
  event.preventDefault();
  event.stopPropagation();
  var canvas = binding.host.closest<HTMLElement>(".slide-canvas");
  if (!canvas) return;
  var canvasRect = canvas.getBoundingClientRect();
  var hostRect = binding.host.getBoundingClientRect();
  beginChange();
  regionGesture = {
    kind: kind,
    binding: binding,
    canvas: canvas,
    canvasRect: canvasRect,
    hostRect: hostRect,
    startX: event.clientX,
    startY: event.clientY,
    region: regionFromBinding(binding)
  };
  document.body.classList.add(kind === "move" ? "moving-text-region" : "resizing-text-region");
  document.addEventListener("pointermove", moveTextRegionGesture);
  document.addEventListener("pointerup", finishTextRegionGesture, {once: true});
  document.addEventListener("pointercancel", finishTextRegionGesture, {once: true});
}

function moveTextRegionGesture(event: PointerEvent) {
  if (!regionGesture) return;
  event.preventDefault();
  var gesture = regionGesture;
  var scale = canvasRenderScale(gesture.canvas);
  var dx = event.clientX - gesture.startX;
  var dy = event.clientY - gesture.startY;
  var next = Object.assign({}, gesture.region);
  if (gesture.kind === "move") {
    dx = Math.max(gesture.canvasRect.left - gesture.hostRect.left,
      Math.min(gesture.canvasRect.right - gesture.hostRect.right, dx));
    dy = Math.max(gesture.canvasRect.top - gesture.hostRect.top,
      Math.min(gesture.canvasRect.bottom - gesture.hostRect.bottom, dy));
    next.x = gesture.region.x + dx / scale.x;
    next.y = gesture.region.y + dy / scale.y;
  } else {
    var maxWidth = gesture.canvasRect.right - gesture.hostRect.left;
    var maxHeight = gesture.canvasRect.bottom - gesture.hostRect.top;
    next.width = Math.max(48, Math.min(maxWidth / scale.x,
      gesture.region.width + dx / scale.x));
    next.height = Math.max(28, Math.min(maxHeight / scale.y,
      gesture.region.height + dy / scale.y));
  }
  next = {
    x: Math.round(next.x * 10) / 10,
    y: Math.round(next.y * 10) / 10,
    width: Math.round(next.width * 10) / 10,
    height: Math.round(next.height * 10) / 10
  };
  updateOverlay(gesture.binding.slideId, gesture.binding.componentId, "region", next);
  applyTextRegion(gesture.binding);
  syncTextRegionFrame();
}

function finishTextRegionGesture() {
  document.removeEventListener("pointermove", moveTextRegionGesture);
  document.removeEventListener("pointerup", finishTextRegionGesture);
  document.removeEventListener("pointercancel", finishTextRegionGesture);
  document.body.classList.remove("moving-text-region");
  document.body.classList.remove("resizing-text-region");
  if (!regionGesture) return;
  regionGesture = null;
  persist();
}


return {bindTextRegion,applyAllTextRegions,syncTextRegionFrame,removeTextRegionFrame,
  clearTextRegions() {textRegionBindings.clear(); removeTextRegionFrame();}};
}

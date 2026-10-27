export const CANONICAL_SLIDE_WIDTH = 1920, CANONICAL_SLIDE_HEIGHT = 1080;
const EDITOR_MAX_SLIDE_WIDTH = 1280;
interface ViewportHost {
 stage:HTMLElement; stageWrap:HTMLElement; presentationExit:HTMLElement; fullscreenToggle:HTMLElement;
 applyAllTextRegions():void; syncTextRegionFrame():void; showToast(message:string):void;
 canPresent():boolean; modeChanged():void;
}
export function createViewport({stage,stageWrap,presentationExit,fullscreenToggle,applyAllTextRegions,syncTextRegionFrame,showToast,canPresent,modeChanged}:ViewportHost) {
let presentationExitTimer: ReturnType<typeof setTimeout> | undefined;
const review = new URLSearchParams(location.search);
let reading = !document.body.classList.contains('preview-only') && review.get('read') === '1';
const bounded = (value:number, minimum:number, maximum:number) => Number.isFinite(value) ? Math.max(minimum, Math.min(maximum, value)) : minimum;
// At half of the original 1920 px canvas, a 24 px chart label is 12 CSS px.
// Reading scale is independent of the fit scale and never edits slide state.
let readingScale = bounded(Number(review.get('zoom') || .5), .5, 1.5);
let pendingScroll:{left:number;top:number}|null = reading ? {
 left:bounded(Number(review.get('x')),0,CANONICAL_SLIDE_WIDTH)*readingScale,
 top:bounded(Number(review.get('y')),0,CANONICAL_SLIDE_HEIGHT)*readingScale
} : null;
let fitFrame = 0;
let reviewTimer:ReturnType<typeof setTimeout>|undefined;
const readingToggles = document.querySelectorAll<HTMLButtonElement>('[data-reading-toggle]');
const zoomIn = document.querySelector<HTMLButtonElement>('[data-reading-in]');
const zoomOut = document.querySelector<HTMLButtonElement>('[data-reading-out]');
const zoomLabel = document.querySelector<HTMLOutputElement>('[data-reading-scale]');
const pointers = new Map<number,{x:number;y:number}>();
const readingControl = (target:EventTarget|null) => target instanceof Element &&
 !!target.closest('button,input,select,textarea,a,label,[role="button"],[role="tab"]');
let gesture:{left:number;top:number;x:number;y:number;distance:number;scale:number}|null = null;
function syncReading() {
 document.body.classList.toggle('read-mode', reading);
 readingToggles.forEach(button => {button.textContent=reading?'Fit':'Read';button.setAttribute('aria-pressed',String(reading));});
 if(zoomIn) {zoomIn.hidden=!reading;zoomIn.disabled=readingScale>=1.5;}
 if(zoomOut) {zoomOut.hidden=!reading;zoomOut.disabled=readingScale<=.5;}
 if(zoomLabel) {zoomLabel.hidden=!reading;zoomLabel.value=Math.round(readingScale*100)+'%';}
}
function saveReview() {
 clearTimeout(reviewTimer);
 // Save a settled view, rather than sending history mutations on every frame.
 reviewTimer=setTimeout(() => {
  const url=new URL(location.href);
  for(const key of ['read','zoom','x','y']) url.searchParams.delete(key);
  if(reading) {
   url.searchParams.set('read','1');url.searchParams.set('zoom',String(readingScale));
   url.searchParams.set('x',String(Math.round(stageWrap.scrollLeft/readingScale)));
   url.searchParams.set('y',String(Math.round(stageWrap.scrollTop/readingScale)));
  }
  history.replaceState(null,'',url.pathname+url.search+url.hash);
 },200);
}
function applyPendingScroll() {
 if(pendingScroll) {stageWrap.scrollLeft=pendingScroll.left;stageWrap.scrollTop=pendingScroll.top;pendingScroll=null;}
}
function zoomReading(scale:number, x=stageWrap.clientWidth/2, y=stageWrap.clientHeight/2) {
 if(!reading) return;
 applyPendingScroll();
 const padding=getComputedStyle(stageWrap), left=parseFloat(padding.paddingLeft), top=parseFloat(padding.paddingTop);
 const next=bounded(Math.round(scale*1000)/1000,.5,1.5);
 pendingScroll={left:(stageWrap.scrollLeft+x-left)*next/readingScale-x+left,
  top:(stageWrap.scrollTop+y-top)*next/readingScale-y+top};
 readingScale=next;syncReading();fitStage();
}
function setReadingMode(enabled:boolean) {
 if(enabled && !setPresentationMode(true)) return;
 if(enabled) readingScale=bounded(Math.max(readingScale,Number(stage.dataset.stageScale)||.5),.5,1.5);
 reading=enabled;pointers.clear();gesture=null;
 pendingScroll={left:0,top:0};syncReading();fitStage();saveReview();
}
readingToggles.forEach(button => button.addEventListener('click',() => setReadingMode(!reading)));
zoomIn?.addEventListener('click',() => zoomReading(readingScale*1.25));
zoomOut?.addEventListener('click',() => zoomReading(readingScale/1.25));
stageWrap.addEventListener('scroll',() => {if(reading) saveReview();},{passive:true});
function resetGesture() {
 const points=[...pointers.values()];
 gesture=points.length ? {left:stageWrap.scrollLeft,top:stageWrap.scrollTop,
  x:points.reduce((sum,p)=>sum+p.x,0)/points.length,y:points.reduce((sum,p)=>sum+p.y,0)/points.length,
  distance:points.length===2?Math.max(1,Math.hypot(points[1].x-points[0].x,points[1].y-points[0].y)):1,
  scale:readingScale} : null;
}
stageWrap.addEventListener('pointerdown',event => {
 if(!reading || event.button>0 || pointers.size>=2 || readingControl(event.target)) return;
 applyPendingScroll();
 pointers.set(event.pointerId,{x:event.clientX,y:event.clientY});resetGesture();
 stageWrap.setPointerCapture(event.pointerId);event.preventDefault();event.stopPropagation();
},true);
stageWrap.addEventListener('pointermove',event => {
 if(!reading || !pointers.has(event.pointerId) || !gesture) return;
 pointers.set(event.pointerId,{x:event.clientX,y:event.clientY});
 const points=[...pointers.values()];
 const x=points.reduce((sum,p)=>sum+p.x,0)/points.length,y=points.reduce((sum,p)=>sum+p.y,0)/points.length;
 if(points.length===2) {
  const box=stageWrap.getBoundingClientRect(),padding=getComputedStyle(stageWrap);
  const left=parseFloat(padding.paddingLeft),top=parseFloat(padding.paddingTop);
  readingScale=bounded(Math.round(gesture.scale*Math.hypot(points[1].x-points[0].x,points[1].y-points[0].y)/gesture.distance*1000)/1000,.5,1.5);
  pendingScroll={left:(gesture.left+gesture.x-box.left-left)*readingScale/gesture.scale-(x-box.left)+left,
   top:(gesture.top+gesture.y-box.top-top)*readingScale/gesture.scale-(y-box.top)+top};
  syncReading();fitStage();
 } else {stageWrap.scrollLeft=gesture.left+gesture.x-x;stageWrap.scrollTop=gesture.top+gesture.y-y;}
 event.preventDefault();event.stopPropagation();
},true);
for(const eventName of ['pointerup','pointercancel','lostpointercapture']) stageWrap.addEventListener(eventName,event => {
 if(pointers.delete((event as PointerEvent).pointerId)) resetGesture();
});
// Pointer capture does not consume the parallel legacy touch stream. Plotly
// listens to that stream and would zoom its axes during a canvas pan/pinch.
// The reader owns these gestures; native controls retain their ordinary taps.
for(const eventName of ['touchstart','touchmove','touchend','touchcancel']) stageWrap.addEventListener(eventName,event => {
 if(!reading || readingControl(event.target)) return;
 event.preventDefault();event.stopPropagation();
},{capture:true,passive:false});
stageWrap.addEventListener('wheel',event => {
 if(reading && (event.ctrlKey || event.metaKey)) {
  const box=stageWrap.getBoundingClientRect();
  zoomReading(readingScale*Math.exp(-event.deltaY/500),event.clientX-box.left,event.clientY-box.top);event.preventDefault();
 }
},{passive:false});
function panReading(event:KeyboardEvent) {
 if(!reading || event.ctrlKey || event.metaKey || event.altKey || !['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)) return false;
 stageWrap.scrollBy({left:event.key==='ArrowLeft'?-stageWrap.clientWidth/2:event.key==='ArrowRight'?stageWrap.clientWidth/2:0,
  top:event.key==='ArrowUp'?-stageWrap.clientHeight/2:event.key==='ArrowDown'?stageWrap.clientHeight/2:0});
 event.preventDefault();event.stopPropagation();return true;
}
syncReading();
const navigatorToggle = document.querySelector<HTMLButtonElement>('[data-slides-toggle]');
function closeNavigator() {
  document.body.classList.remove('navigator-open');
  navigatorToggle?.setAttribute('aria-expanded', 'false');
  if (navigatorToggle) navigatorToggle.textContent = 'Slides';
}
navigatorToggle?.addEventListener('click', () => {
  const open = document.body.classList.toggle('navigator-open');
  navigatorToggle.setAttribute('aria-expanded', String(open));
  navigatorToggle.textContent = open ? 'Close slides' : 'Slides';
  if (open) document.querySelector('.thumb.current')?.scrollIntoView({block:'nearest'});
});
document.querySelector('[data-slides-dismiss]')?.addEventListener('click', closeNavigator);
document.addEventListener('keydown', event => {if (event.key === 'Escape') closeNavigator();});
matchMedia('(max-width: 960px)').addEventListener('change', closeNavigator);
function stageContentBox() {
  var style = getComputedStyle(stageWrap);
  return {
    width: Math.max(0, stageWrap.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight)),
    height: Math.max(0, stageWrap.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom))
  };
}

function fitStage() {
  var available = stageContentBox();
  if (!available.width || !available.height) return;
  var presentation = document.body.classList.contains("present-only");
  var width = presentation ? available.width : Math.min(available.width, EDITOR_MAX_SLIDE_WIDTH);
  var scale = reading ? readingScale : Math.min(width / CANONICAL_SLIDE_WIDTH, available.height / CANONICAL_SLIDE_HEIGHT);
  if (!Number.isFinite(scale) || scale <= 0) return;
  stage.style.width = (CANONICAL_SLIDE_WIDTH * scale).toFixed(2) + "px";
  stage.style.height = (CANONICAL_SLIDE_HEIGHT * scale).toFixed(2) + "px";
  stage.style.setProperty("--stage-scale", String(scale));
  stage.dataset.stageFit = reading ? "reading" : "uniform-contain";
  stage.dataset.stageScale = scale.toFixed(6);
  if(fitFrame) cancelAnimationFrame(fitFrame);
  fitFrame=requestAnimationFrame(function () {
    fitFrame=0;
    applyPendingScroll();
    applyAllTextRegions();
    syncTextRegionFrame();
    if(reading) saveReview();
  });
}

function revealPresentationExit() {
  if (!document.body.classList.contains("present-only")) return;
  presentationExit.classList.add("visible");
  clearTimeout(presentationExitTimer);
  presentationExitTimer = setTimeout(function () {
    presentationExit.classList.remove("visible");
  }, 2400);
}

function removePresentationQuery() {
  var url = new URL(location.href);
  url.searchParams.delete("present");
  for(const key of ['read','zoom','x','y']) url.searchParams.delete(key);
  history.replaceState(null, "", url.pathname + url.search + url.hash);

}

function setPresentationMode(enabled: boolean) {
  closeNavigator();
  if(enabled && !canPresent()) {showToast('No visible slides. Show a slide before presenting.');return false;}
  const changed=document.body.classList.contains('present-only')!==enabled;
  document.body.classList.toggle("present-only", enabled);
  if(!enabled) {reading=false;pointers.clear();gesture=null;syncReading();saveReview();}
  fullscreenToggle.textContent = enabled ? "Exit presentation" : "Present fullscreen";
  requestAnimationFrame(fitStage);
  if (enabled) revealPresentationExit();
  else {
    clearTimeout(presentationExitTimer);
    presentationExit.classList.remove("visible");
  }
  if(changed) modeChanged();
  return true;
}

function exitFullscreenPresentation() {
  removePresentationQuery();
  setPresentationMode(false);
  if (document.fullscreenElement && document.exitFullscreen) {
    var request = document.exitFullscreen();
    if (request && request.catch) request.catch(function () {});
  }
}

function toggleFullscreenPresentation() {
  if (document.fullscreenElement || document.body.classList.contains("present-only")) {
    exitFullscreenPresentation();
    return;
  }
  if(!setPresentationMode(true)) return;
  var request = document.documentElement.requestFullscreen && document.documentElement.requestFullscreen();
  if (request && request.catch) {
    request.catch(function () {
      showToast("Presentation view is active. Use the browser fullscreen control if needed.");
    });
  }
}


return {fitStage,revealPresentationExit,removePresentationQuery,setPresentationMode,exitFullscreenPresentation,toggleFullscreenPresentation,closeNavigator,panReading};
}

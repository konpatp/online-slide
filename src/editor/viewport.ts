export const CANONICAL_SLIDE_WIDTH = 1920, CANONICAL_SLIDE_HEIGHT = 1080;
const EDITOR_MAX_SLIDE_WIDTH = 1280;
interface ViewportHost {
 stage:HTMLElement; stageWrap:HTMLElement; presentationExit:HTMLElement; fullscreenToggle:HTMLElement;
 applyAllTextRegions():void; syncTextRegionFrame():void; showToast(message:string):void;
}
export function createViewport({stage,stageWrap,presentationExit,fullscreenToggle,applyAllTextRegions,syncTextRegionFrame,showToast}:ViewportHost) {
let presentationExitTimer: ReturnType<typeof setTimeout> | undefined;
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
  var scale = Math.min(width / CANONICAL_SLIDE_WIDTH, available.height / CANONICAL_SLIDE_HEIGHT);
  if (!Number.isFinite(scale) || scale <= 0) return;
  stage.style.width = (CANONICAL_SLIDE_WIDTH * scale).toFixed(2) + "px";
  stage.style.height = (CANONICAL_SLIDE_HEIGHT * scale).toFixed(2) + "px";
  stage.style.setProperty("--stage-scale", String(scale));
  stage.dataset.stageFit = "uniform-contain";
  stage.dataset.stageScale = scale.toFixed(6);
  requestAnimationFrame(function () {
    applyAllTextRegions();
    syncTextRegionFrame();
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
  history.replaceState(null, "", url.pathname + url.search + url.hash);

}

function setPresentationMode(enabled: boolean) {
  document.body.classList.toggle("present-only", enabled);
  fullscreenToggle.textContent = enabled ? "Exit presentation" : "Present fullscreen";
  requestAnimationFrame(fitStage);
  if (enabled) revealPresentationExit();
  else {
    clearTimeout(presentationExitTimer);
    presentationExit.classList.remove("visible");
  }
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
  setPresentationMode(true);
  var request = document.documentElement.requestFullscreen && document.documentElement.requestFullscreen();
  if (request && request.catch) {
    request.catch(function () {
      showToast("Presentation view is active. Use the browser fullscreen control if needed.");
    });
  }
}


return {fitStage,revealPresentationExit,removePresentationQuery,setPresentationMode,exitFullscreenPresentation,toggleFullscreenPresentation};
}

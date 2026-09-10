interface FitOptions { minSize?: number; mode?: string; property?: string; minScale?: number; maxScale?: number; tolerance?: number; contentSelector?: string }
let fitObservers: ResizeObserver[] = [];
export function trackFitObserver(observer: ResizeObserver): void { fitObservers.push(observer); }

export function fitTextInRegion(element: HTMLElement, region: HTMLElement, options: FitOptions = {}) {
  options = options || {};
  if (!element.isConnected || region.clientWidth < 1 || region.clientHeight < 1) return;
  element.style.removeProperty("font-size");
  var maxSize = Number(element.dataset.fitMaxSize || parseFloat(getComputedStyle(element).fontSize));
  element.dataset.fitMaxSize = String(maxSize);
  var minSize = Math.min(maxSize, options.minSize || 20);
  var fits = function (size: number) {
    element.style.fontSize = size + "px";
    return element.scrollWidth <= region.clientWidth + 1 && element.scrollHeight <= region.clientHeight + 1;
  };
  var low = minSize;
  var high = maxSize;
  var best = minSize;
  if (fits(maxSize)) best = maxSize;
  else {
    for (var index = 0; index < 10; index += 1) {
      var candidate = (low + high) / 2;
      if (fits(candidate)) { best = candidate; low = candidate; }
      else high = candidate;
    }
  }
  element.style.fontSize = best.toFixed(2) + "px";
  while (best > minSize &&
         (element.scrollWidth > region.clientWidth + 1 || element.scrollHeight > region.clientHeight + 1)) {
    best = Math.max(minSize, best - 0.25);
    element.style.fontSize = best.toFixed(2) + "px";
  }
  var style = getComputedStyle(element);
  var lineHeight = parseFloat(style.lineHeight) || best;
  var verticalPadding = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
  var lineCount = Math.max(1, Math.round((element.scrollHeight - verticalPadding) / lineHeight));
  var contained = element.scrollWidth <= region.clientWidth + 1 && element.scrollHeight <= region.clientHeight + 1;
  element.dataset.fitMode = options.mode || "text-region";
  element.dataset.fitFontSize = best.toFixed(2);
  element.dataset.fitLines = String(lineCount);
  element.dataset.fitOverflow = String(!contained);
}

export function registerTextFit(element: HTMLElement, region: HTMLElement, options: FitOptions = {}) {
  var fit = function () { requestAnimationFrame(function () { fitTextInRegion(element, region, options); }); };
  var observer = new ResizeObserver(fit);
  observer.observe(region);
  fitObservers.push(observer);
  element.addEventListener("input", fit);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit);
  fit();
}

export function fitGroupInRegion(element: HTMLElement, region: HTMLElement, options: FitOptions = {}) {
  options = options || {};
  if (!element.isConnected || region.clientWidth < 1 || region.clientHeight < 1) return;
  var property = options.property || "--region-fit-scale";
  var minScale = options.minScale || 0.58;
  var maxScale = options.maxScale || 1;
  // KaTeX's hidden MathML/HTML pairing can report a 1–2 px scroll-height
  // surplus even when its visible box is fully contained. Treat only a
  // material surplus as overflow so a harmless rounding artifact cannot
  // force an entire table to its minimum scale.
  var tolerance = options.tolerance || 3;
  var leaves = function () {
    return options.contentSelector ? Array.from(element.querySelectorAll<HTMLElement>(options.contentSelector)) : [];
  };
  var leafFits = function (leaf: HTMLElement) {
    var math=leaf.querySelector('.katex-html'),cell=leaf.closest<HTMLElement>('td,th');
    if(math && cell) {
      // KaTeX's accessibility/strut boxes can exceed the text leaf's
      // scrollHeight while the visible formula fits its padded table cell.
      // Judge rendered mathematics in that actual allocation, not hidden
      // MathML dimensions; long formulae still fail horizontal containment.
      var ink=math.getBoundingClientRect(),box=cell.getBoundingClientRect();
      var scale=box.width/cell.offsetWidth,style=getComputedStyle(cell);
      return ink.left>=box.left+parseFloat(style.paddingLeft)*scale-tolerance &&
        ink.right<=box.right-parseFloat(style.paddingRight)*scale+tolerance &&
        ink.top>=box.top+parseFloat(style.paddingTop)*scale-tolerance &&
        ink.bottom<=box.bottom-parseFloat(style.paddingBottom)*scale+tolerance;
    }
    return leaf.scrollWidth <= leaf.clientWidth + tolerance && leaf.scrollHeight <= leaf.clientHeight + tolerance;
  };
  var fits = function (scale: number) {
    element.style.setProperty(property, scale.toFixed(4));
    var box = element.getBoundingClientRect();
    var outer = region.getBoundingClientRect();
    var contained = box.width <= outer.width + tolerance && box.height <= outer.height + tolerance;
    return contained && element.scrollWidth <= element.clientWidth + tolerance &&
      element.scrollHeight <= element.clientHeight + tolerance && leaves().every(leafFits);
  };
  var low = minScale;
  var high = maxScale;
  var best = minScale;
  if (fits(maxScale)) best = maxScale;
  else {
    for (var index = 0; index < 10; index += 1) {
      var candidate = (low + high) / 2;
      if (fits(candidate)) { best = candidate; low = candidate; }
      else high = candidate;
    }
  }
  element.style.setProperty(property, best.toFixed(4));
  var finalBox = element.getBoundingClientRect();
  var finalOuter = region.getBoundingClientRect();
  var overflow = finalBox.width > finalOuter.width + tolerance ||
    finalBox.height > finalOuter.height + tolerance ||
    element.scrollWidth > element.clientWidth + tolerance ||
    element.scrollHeight > element.clientHeight + tolerance ||
    leaves().some(function (leaf) {return !leafFits(leaf);});
  element.dataset.fitMode = options.mode || "group-region";
  element.dataset.fitScale = best.toFixed(4);
  element.dataset.fitOverflow = String(overflow);
}

export function registerGroupFit(element: HTMLElement, region: HTMLElement, options: FitOptions = {}) {
  var fit = function () { requestAnimationFrame(function () { fitGroupInRegion(element, region, options); }); };
  var observer = new ResizeObserver(fit);
  observer.observe(region);
  fitObservers.push(observer);
  element.addEventListener("input", fit);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit);
  fit();
}

export function clearFitObservers() {
  fitObservers.forEach(function (observer) { observer.disconnect(); });
  fitObservers = [];
}

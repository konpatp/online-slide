// Recipe owns layout; injected editor capabilities own mutable state.
export function createHierarchicalGallery(api) {
const global = window;
const {editableText,bindTextRegion,galleryImage,effectiveComponent} = api;
function hierarchicalGallery(canvas, slide) {
  var body = document.createElement("div");
  body.className = "recipe-body hierarchical-gallery-body";
  if (!slide.data.selectors.length && Object.values(slide.data.pageSets).every(function (pages) { return pages.length === 1; })) body.classList.add("static-gallery");
  var controls = document.createElement("div");
  controls.className = "gallery-controls";
  var summary = document.createElement("div");
  summary.className = "gallery-summary";
  var viewHost = document.createElement("div");
  viewHost.className = "hierarchical-gallery-view";
  var storageKey = "online-slide.gallery." + slide.id;
  var defaults = {};
  slide.data.selectors.forEach(function (selector) { defaults[selector.id] = selector.options[0].value; });
  Object.assign(defaults, slide.data.initialSelection || {});
  var saved = {};
  try { saved = JSON.parse(localStorage.getItem(storageKey) || "{}"); } catch (_) { saved = {}; }
  var galleryState = {selection: Object.assign(defaults, saved.selection || {}), page: Number(saved.page || 0)};

  function componentText(componentId) { return effectiveComponent(slide, componentId).text; }
  function activeView() {
    return slide.data.views.find(function (view) {
      return slide.data.selectors.every(function (selector) {
        return view.selection[selector.id] === galleryState.selection[selector.id];
      });
    }) || slide.data.views[0];
  }
  function saveGalleryState() {
    localStorage.setItem(storageKey, JSON.stringify(galleryState));
  }
  function renderGallery() {
    global.renderScientificFacetControls(controls, slide, slide.data.selectors, galleryState.selection, function (key, value) {
      galleryState.selection[key] = value;
      galleryState.page = 0;
      saveGalleryState();
      renderGallery();
    });

    var view = activeView();
    var columns = view.columns || slide.data.columns;
    var viewPages = slide.data.pageSets[view.pageSet];
    galleryState.page = Math.max(0, Math.min(viewPages.length - 1, galleryState.page));
    var page = viewPages[galleryState.page];
    summary.textContent = "";
    summary.appendChild(editableText(slide, view.classLabel, "div", "gallery-class-name"));
    summary.appendChild(editableText(slide, view.metric, "div", "gallery-metric"));
    var pages = document.createElement("div");
    pages.className = "gallery-pages";
    viewPages.forEach(function (candidate, index) {
      var button = document.createElement("button");
      button.type = "button";
      button.textContent = componentText(candidate.label);
      button.setAttribute("aria-pressed", String(index === galleryState.page));
      button.addEventListener("click", function (event) {
        event.stopPropagation();
        galleryState.page = index;
        saveGalleryState();
        renderGallery();
      });
      pages.appendChild(button);
    });
    summary.appendChild(pages);

    viewHost.textContent = "";
    var grid = document.createElement("div");
    grid.className = "hierarchical-gallery-grid";
    if (columns.every(function (key) { return !componentText(key).trim(); })) grid.classList.add("without-column-labels");
    if (page.rows.every(function (row) { return !componentText(row.label).trim() && !row.detail; })) grid.classList.add("without-identities");
    grid.style.setProperty("--gallery-columns", String(columns.length));
    grid.style.setProperty("--gallery-rows", String(page.rows.length));
    var corner = document.createElement("div"); corner.className="gallery-corner"; grid.appendChild(corner);
    columns.forEach(function (componentId) {
      var frame = document.createElement("div"); frame.className = "gallery-heading-region";
      var heading = editableText(slide, componentId, "div", "gallery-heading");
      frame.appendChild(heading); grid.appendChild(frame);
      bindTextRegion(slide, componentId, heading, frame, {alwaysFit:true,fitMode:"gallery-heading-region",minSize:30});
    });
    page.rows.forEach(function (row) {
      var frame = document.createElement("div"); frame.className = "gallery-identity-region";
      var label = editableText(slide, row.label, "div", "gallery-row-label");
      frame.appendChild(label);
      if (row.detail) frame.appendChild(editableText(slide,row.detail,"div","gallery-row-detail"));
      grid.appendChild(frame);
      bindTextRegion(slide,row.label,label,frame,{alwaysFit:true,fitMode:"gallery-identity-region",minSize:30});
      row.images.forEach(function (componentId) { grid.appendChild(galleryImage(slide, componentId)); });
    });
    viewHost.appendChild(grid);
  }
  body.appendChild(controls);
  body.appendChild(summary);
  body.appendChild(viewHost);
  canvas.appendChild(body);
  renderGallery();
}


return hierarchicalGallery;
}

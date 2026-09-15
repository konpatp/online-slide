// Recipe owns layout; injected editor capabilities own mutable state.
export function createHierarchicalGallery(api) {
const global = window;
const {editableText,bindTextRegion,galleryImage,effectiveComponent} = api;
function hierarchicalGallery(canvas, slide) {
  var body = document.createElement("div");
  body.className = "recipe-body hierarchical-gallery-body";
  if (slide.data.paired) body.classList.add("paired-gallery");
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
    if (viewPages.length > 1 || !slide.data.paired) summary.appendChild(pages);

    viewHost.textContent = "";
    if (slide.data.paired) {
      var wall = document.createElement("div");
      wall.className = "paired-gallery-wall";
      wall.style.setProperty("--pair-columns", String(columns.length / 2));
      wall.style.setProperty("--pair-rows", String(page.rows.length));
      for (let column = 0; column < columns.length; column += 2) {
        var group = document.createElement("div"); group.className = "paired-gallery-group";
        var headings = document.createElement("div"); headings.className = "paired-gallery-headings";
        [column, column + 1].forEach(function (index) {
          headings.appendChild(editableText(slide, columns[index], "div", "gallery-heading"));
        });
        group.appendChild(headings);
        page.rows.forEach(function (row) {
          var ids = row.images.slice(column, column + 2);
          if (!ids.length) return;
          var pair = document.createElement("div"); pair.className = "gallery-pair";
          var pictures = document.createElement("div"); pictures.className = "gallery-pair-pictures";
          ids.forEach(function (id) {
            var cell = galleryImage(slide, id);
            cell.querySelector(".gallery-caption-frame")?.remove();
            pictures.appendChild(cell);
          });
          pair.appendChild(pictures);
          var captionId = effectiveComponent(slide, ids[0]).caption;
          var captionFrame = document.createElement("div"); captionFrame.className = "gallery-pair-caption-frame";
          if (captionId) {
            var caption = editableText(slide, captionId, "div", "gallery-pair-caption");
            captionFrame.appendChild(caption);
            bindTextRegion(slide, captionId, caption, captionFrame, {alwaysFit:true, minSize:18, fitMode:"pair-caption"});
          }
          pair.appendChild(captionFrame);
          pictures.setAttribute("role", "button"); pictures.tabIndex = 0;
          pictures.setAttribute("aria-label", "Enlarge matched pair: " + (captionId ? componentText(captionId) : effectiveComponent(slide, ids[0]).alt));
          function enlarge(event) {
            if (canvas.closest(".edit-mode")) return;
            event.stopPropagation();
            var dialog = document.createElement("dialog"); dialog.className = "gallery-pair-dialog";
            var close = document.createElement("button"); close.textContent = "Close ×";
            close.addEventListener("click", function () { dialog.close(); });
            dialog.appendChild(close);
            var title = document.createElement("h2");
            title.textContent = captionId ? componentText(captionId) : "Matched pair";
            dialog.appendChild(title);
            var images = document.createElement("div"); images.className = "gallery-pair-enlarged";
            ids.forEach(function (id, index) {
              var figure = document.createElement("figure");
              var label = document.createElement("figcaption"); label.textContent = componentText(columns[column + index]);
              var img = document.createElement("img"); var source = effectiveComponent(slide, id);
              img.src = source.src; img.alt = source.alt;
              figure.appendChild(label); figure.appendChild(img); images.appendChild(figure);
            });
            dialog.appendChild(images); canvas.appendChild(dialog);
            dialog.addEventListener("keydown", function (e) { e.stopPropagation(); });
            dialog.addEventListener("close", function () { dialog.remove(); pictures.focus(); });
            dialog.showModal();
          }
          pictures.addEventListener("click", enlarge);
          pictures.addEventListener("keydown", function (event) {
            if (event.key === "Enter" || event.key === " ") { event.preventDefault(); enlarge(event); }
          });
          group.appendChild(pair);
        });
        wall.appendChild(group);
      }
      viewHost.appendChild(wall);
      return;
    }
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

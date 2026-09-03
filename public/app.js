/* ScientificSlideKit pilot: declarative recipes plus a bundled diagram engine. */
(function () {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";
  var enteredFromPresentationUrl = new URLSearchParams(location.search).get("present") === "1";
  if (enteredFromPresentationUrl) {
    document.body.classList.add("present-only");
  }
  var stage = document.querySelector("[data-stage]");
  var thumbList = document.querySelector("[data-thumb-list]");
  var count = document.querySelector("[data-slide-count]");
  var position = document.querySelector("[data-position]");
  var status = document.querySelector("[data-save-state]");
  var editToggle = document.querySelector("[data-edit-toggle]");
  var fullscreenToggle = document.querySelector("[data-fullscreen-toggle]");
  var presentationExit = document.querySelector("[data-presentation-exit]");
  var undoButton = document.querySelector("[data-undo]");
  var toast = document.querySelector("[data-toast]");
  var selectedLabel = document.querySelector("[data-selected-component]");
  var state = null;
  var accepted = null;
  var currentId = null;
  var selected = null;
  var editMode = false;
  var pending = null;
  var inFlight = null;
  var undoBase = null;
  var inputTimer = null;
  var toastTimer = null;
  var presentationExitTimer = null;
  var fitObservers = [];

  function copy(value) { return JSON.parse(JSON.stringify(value)); }

  function snapshot(value) {
    return {
      schema: value.schema,
      order: value.order.slice(),
      hidden: value.hidden.slice(),
      overlays: copy(value.overlays)
    };
  }

  function sameSnapshot(a, b) {
    return JSON.stringify(snapshot(a)) === JSON.stringify(snapshot(b));
  }

  function setStatus(label, kind) {
    status.textContent = label;
    status.className = "save-state " + (kind || "saved");
  }

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add("visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toast.classList.remove("visible"); }, 2700);
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
    enteredFromPresentationUrl = false;
  }

  function setPresentationMode(enabled) {
    document.body.classList.toggle("present-only", enabled);
    fullscreenToggle.textContent = enabled ? "Exit presentation" : "Present fullscreen";
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

  function slideById(id) { return state.slides[id]; }
  function currentSlide() { return slideById(currentId); }
  function currentIndex() {
    var index = state.order.indexOf(currentId);
    return index < 0 ? 0 : index;
  }

  function overlayFor(slideId, componentId, create) {
    if (!state.overlays[slideId]) {
      if (!create) return {};
      state.overlays[slideId] = {};
    }
    if (!state.overlays[slideId][componentId]) {
      if (!create) return {};
      state.overlays[slideId][componentId] = {};
    }
    return state.overlays[slideId][componentId];
  }

  function effectiveComponent(slide, componentId) {
    var source = slide.components[componentId];
    var overlay = overlayFor(slide.id, componentId, false);
    return Object.assign({}, source, overlay);
  }

  function cleanOverlay(slideId, componentId) {
    var slideOverlays = state.overlays[slideId];
    if (!slideOverlays) return;
    if (Object.keys(slideOverlays[componentId] || {}).length === 0) delete slideOverlays[componentId];
    if (Object.keys(slideOverlays).length === 0) delete state.overlays[slideId];
  }

  function updateOverlay(slideId, componentId, key, value) {
    var source = state.slides[slideId].components[componentId];
    var overlay = overlayFor(slideId, componentId, true);
    if (source[key] === value || value === undefined || value === null) delete overlay[key];
    else overlay[key] = value;
    cleanOverlay(slideId, componentId);
  }

  function beginChange() {
    if (!undoBase) undoBase = copy(accepted);
    undoButton.disabled = false;
    setStatus("Saving…", "saving");
  }

  function persist() {
    pending = snapshot(state);
    setStatus("Saving…", "saving");
    flush();
  }

  function flush() {
    if (inFlight || !pending) return;
    var job = pending;
    pending = null;
    inFlight = job;
    fetch("api/deck-state", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        baseRevision: accepted.revision,
        baseSourceRevision: accepted.sourceRevision,
        snapshot: job
      })
    }).then(function (response) {
      return response.json().then(function (payload) {
        return {ok: response.ok, status: response.status, payload: payload};
      });
    }).then(function (result) {
      inFlight = null;
      if (!result.ok) {
        if (result.status === 409 && result.payload.state) {
          accepted = result.payload.state;
          state = copy(accepted);
          pending = null;
          undoBase = null;
          selected = null;
          render();
          setStatus("Conflict · reloaded", "error");
          showToast("Source or another editor changed first; the accepted state is shown.");
        } else {
          pending = job;
          setStatus("Offline · retrying", "error");
          setTimeout(flush, 1400);
        }
        return;
      }
      accepted = result.payload;
      if (!pending && sameSnapshot(state, accepted)) {
        state = copy(accepted);
        undoBase = null;
        render();
        setStatus("Saved", "saved");
      } else {
        setStatus("Saving…", "saving");
        flush();
      }
    }).catch(function () {
      inFlight = null;
      pending = job;
      setStatus("Offline · retrying", "error");
      setTimeout(flush, 1400);
    });
  }

  function svgElement(name, attrs) {
    var node = document.createElementNS(SVG_NS, name);
    Object.keys(attrs || {}).forEach(function (key) { node.setAttribute(key, attrs[key]); });
    return node;
  }

  function applyComponentStyle(element, component) {
    if (component.color) element.style.color = component.color;
    if (component.fontScale) element.style.setProperty("--component-scale", component.fontScale);
  }

  function editableText(slide, componentId, tag, className) {
    var component = effectiveComponent(slide, componentId);
    var element = document.createElement(tag || "div");
    element.className = (className || "") + " semantic-component";
    var isLatex = component.render === "latex";
    if (isLatex) {
      if (!window.ScientificMathRuntime) throw new Error("KaTeX math runtime is missing");
      window.ScientificMathRuntime.renderLatex(element, component.text, {displayMode: component.display === "block"});
      element.setAttribute("data-latex-source", component.text);
    } else {
      element.textContent = component.text;
    }
    element.setAttribute("data-component-id", componentId);
    element.setAttribute("data-component-kind", "text");
    element.setAttribute("aria-label", component.role || componentId);
    element.contentEditable = editMode && !isLatex ? "true" : "false";
    applyComponentStyle(element, component);
    element.addEventListener("click", function (event) {
      if (!editMode) return;
      event.stopPropagation();
      selectComponent(slide.id, componentId, element);
    });
    element.addEventListener("input", function () {
      if (!editMode || isLatex) return;
      updateOverlay(slide.id, componentId, "text", element.textContent.trim());
      beginChange();
      clearTimeout(inputTimer);
      inputTimer = setTimeout(persist, 260);
    });
    element.addEventListener("dblclick", function (event) {
      if (!editMode || !isLatex) return;
      event.stopPropagation();
      var source = window.prompt("Edit LaTeX", effectiveComponent(slide, componentId).text);
      if (source === null) return;
      beginChange();
      updateOverlay(slide.id, componentId, "text", source.trim());
      render();
      persist();
    });
    return element;
  }

  function fitTextInRegion(element, region, options) {
    options = options || {};
    if (!element.isConnected || region.clientWidth < 1 || region.clientHeight < 1) return;
    element.style.removeProperty("font-size");
    var maxSize = Number(element.dataset.fitMaxSize || parseFloat(getComputedStyle(element).fontSize));
    element.dataset.fitMaxSize = String(maxSize);
    var minSize = Math.min(maxSize, options.minSize || 20);
    var fits = function (size) {
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

  function registerTextFit(element, region, options) {
    var fit = function () { requestAnimationFrame(function () { fitTextInRegion(element, region, options); }); };
    var observer = new ResizeObserver(fit);
    observer.observe(region);
    fitObservers.push(observer);
    element.addEventListener("input", fit);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit);
    fit();
  }

  function fitGroupInRegion(element, region, options) {
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
      return options.contentSelector ? Array.from(element.querySelectorAll(options.contentSelector)) : [];
    };
    var fits = function (scale) {
      element.style.setProperty(property, scale.toFixed(4));
      var box = element.getBoundingClientRect();
      var outer = region.getBoundingClientRect();
      var contained = box.width <= outer.width + tolerance && box.height <= outer.height + tolerance;
      return contained && leaves().every(function (leaf) {
        return leaf.scrollWidth <= leaf.clientWidth + tolerance &&
          leaf.scrollHeight <= leaf.clientHeight + tolerance;
      });
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
      leaves().some(function (leaf) {
        return leaf.scrollWidth > leaf.clientWidth + tolerance ||
          leaf.scrollHeight > leaf.clientHeight + tolerance;
      });
    element.dataset.fitMode = options.mode || "group-region";
    element.dataset.fitScale = best.toFixed(4);
    element.dataset.fitOverflow = String(overflow);
  }

  function registerGroupFit(element, region, options) {
    var fit = function () { requestAnimationFrame(function () { fitGroupInRegion(element, region, options); }); };
    var observer = new ResizeObserver(fit);
    observer.observe(region);
    fitObservers.push(observer);
    element.addEventListener("input", fit);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit);
    fit();
  }

  function clearFitObservers() {
    fitObservers.forEach(function (observer) { observer.disconnect(); });
    fitObservers = [];
  }

  function effectiveHeadline(slide) {
    return effectiveComponent(slide, slide.headline).text;
  }

  function slideShell(slide) {
    var canvas = document.createElement("article");
    canvas.className = "slide-canvas recipe-" + slide.recipe;
    canvas.style.setProperty("--accent", slide.theme.accent);
    canvas.setAttribute("data-slide-id", slide.id);
    canvas.addEventListener("click", function () {
      if (editMode) selectComponent(null, null);
    });
    if (state.hidden.indexOf(slide.id) >= 0) {
      var ribbon = document.createElement("span");
      ribbon.className = "hidden-ribbon";
      ribbon.textContent = "Hidden from presentation";
      canvas.appendChild(ribbon);
    }
    var header = document.createElement("header");
    header.className = "recipe-header";
    if (slide.eyebrow) header.appendChild(editableText(slide, slide.eyebrow, "div", "slide-kicker"));
    header.appendChild(editableText(slide, slide.headline, "h1", "slide-title"));
    canvas.appendChild(header);
    return canvas;
  }

  function addFooter(canvas, slide) {
    if (slide.footer) canvas.appendChild(editableText(slide, slide.footer, "div", "protocol-strip"));
    var meta = document.createElement("div");
    meta.className = "slide-meta";
    meta.textContent = slide.recipe + " · " + slide.id;
    canvas.appendChild(meta);
  }

  function uploadImage(slide, componentId, file) {
    if (!file || !file.type.startsWith("image/")) {
      showToast("Drop a PNG, JPEG, WebP, GIF, or SVG image.");
      return;
    }
    setStatus("Uploading…", "saving");
    fetch("api/assets", {method: "POST", headers: {"Content-Type": file.type, "X-File-Name": file.name}, body: file})
      .then(function (response) { return response.json().then(function (payload) { return {ok: response.ok, payload: payload}; }); })
      .then(function (result) {
        if (!result.ok) throw new Error(result.payload.error || "upload failed");
        beginChange();
        updateOverlay(slide.id, componentId, "src", result.payload.src);
        render();
        persist();
        showToast("Image replaced with a content-addressed asset.");
      }).catch(function (error) {
        setStatus("Upload failed", "error");
        showToast(error.message);
      });
  }

  function galleryImage(slide, componentId) {
    var component = effectiveComponent(slide, componentId);
    var cell = document.createElement("div");
    cell.className = "gallery-cell semantic-component";
    cell.setAttribute("data-component-id", componentId);
    cell.setAttribute("data-component-kind", "image");
    cell.setAttribute("aria-label", component.alt);
    var img = document.createElement("img");
    img.src = component.src;
    img.alt = component.alt;
    img.draggable = false;
    img.style.setProperty("--image-scale", component.imageScale || 1);
    cell.appendChild(img);
    if (component.caption) {
      var captionFrame = document.createElement("div");
      captionFrame.className = "gallery-caption-frame";
      var caption = editableText(slide, component.caption, "figcaption", "gallery-cell-caption");
      captionFrame.appendChild(caption);
      cell.appendChild(captionFrame);
      registerTextFit(caption, captionFrame, {mode: "gallery-caption-region", minSize: 12});
    }
    cell.addEventListener("click", function (event) {
      if (!editMode) return;
      event.stopPropagation();
      selectComponent(slide.id, componentId, cell);
    });
    cell.addEventListener("dragover", function (event) {
      if (!editMode) return;
      event.preventDefault();
      cell.classList.add("drop-ready");
    });
    cell.addEventListener("dragleave", function () { cell.classList.remove("drop-ready"); });
    cell.addEventListener("drop", function (event) {
      if (!editMode) return;
      event.preventDefault();
      cell.classList.remove("drop-ready");
      uploadImage(slide, componentId, event.dataTransfer.files[0]);
    });
    return cell;
  }

  var renderRecipe = window.createScientificSlideRecipes({
    svgElement: svgElement,
    editableText: editableText,
    galleryImage: galleryImage,
    effectiveComponent: effectiveComponent,
    fitTextInRegion: registerTextFit,
    fitGroupInRegion: registerGroupFit,
    isEditMode: function () { return editMode; }
  });

  function renderStage() {
    var index = currentIndex();
    currentId = state.order[index];
    var slide = currentSlide();
    clearFitObservers();
    stage.textContent = "";
    var canvas = slideShell(slide);
    renderRecipe[slide.recipe](canvas, slide);
    addFooter(canvas, slide);
    stage.appendChild(canvas);
    stage.classList.toggle("edit-mode", editMode);
    position.textContent = (index + 1) + " / " + state.order.length;
    document.querySelector("[data-prev]").disabled = index === 0;
    document.querySelector("[data-next]").disabled = index === state.order.length - 1;
    if (selected && selected.slideId === currentId) {
      var element = stage.querySelector('[data-component-id="' + selected.componentId + '"]');
      if (element) element.classList.add("selected-component");
    }
  }

  function renderThumbs() {
    thumbList.textContent = "";
    count.textContent = String(state.order.length);
    state.order.forEach(function (id, index) {
      var slide = slideById(id);
      var card = document.createElement("article");
      card.className = "thumb" + (id === currentId ? " current" : "") +
        (state.hidden.indexOf(id) >= 0 ? " hidden" : "");
      card.setAttribute("data-id", id);
      var number = document.createElement("div");
      number.className = "thumb-index";
      number.textContent = String(index + 1).padStart(2, "0");
      card.appendChild(number);
      var inner = document.createElement("div");
      inner.className = "thumb-card";
      var art = document.createElement("div");
      art.className = "thumb-art";
      art.style.setProperty("--thumb-accent", slide.theme.accent);
      var kicker = document.createElement("div");
      kicker.className = "thumb-kicker";
      kicker.textContent = slide.recipe.replaceAll("-", " ");
      var title = document.createElement("div");
      title.className = "thumb-title";
      title.textContent = effectiveHeadline(slide);
      art.appendChild(kicker);
      art.appendChild(title);
      inner.appendChild(art);
      var actions = document.createElement("div");
      actions.className = "thumb-actions";
      [["↑", "move", -1, "Move earlier"], ["↓", "move", 1, "Move later"],
       [state.hidden.indexOf(id) >= 0 ? "◉" : "◌", "visibility", null,
        state.hidden.indexOf(id) >= 0 ? "Show slide" : "Hide slide"]].forEach(function (item) {
        var button = document.createElement("button");
        button.className = "thumb-action " + item[1];
        button.type = "button";
        button.textContent = item[0];
        button.setAttribute("aria-label", item[3]);
        button.setAttribute("data-action", item[1]);
        if (item[2] !== null) button.setAttribute("data-delta", item[2]);
        actions.appendChild(button);
      });
      inner.appendChild(actions);
      card.appendChild(inner);
      thumbList.appendChild(card);
    });
  }

  function selectedComponent() {
    if (!selected || !state.slides[selected.slideId]) return null;
    return effectiveComponent(state.slides[selected.slideId], selected.componentId);
  }

  function renderTools() {
    var component = selectedComponent();
    var textSelected = editMode && component && component.kind === "text";
    var imageSelected = editMode && component && component.kind === "image";
    document.querySelectorAll("[data-font-delta], [data-color]").forEach(function (button) { button.disabled = !textSelected; });
    document.querySelectorAll("[data-image-delta]").forEach(function (button) { button.disabled = !imageSelected; });
    document.querySelector("[data-reset-component]").disabled = !(editMode && component);
    selectedLabel.textContent = component ? selected.slideId + " @ " + selected.componentId : "Select a component in edit mode";
  }

  function render() {
    renderStage();
    renderThumbs();
    renderTools();
    undoButton.disabled = !undoBase;
    editToggle.textContent = editMode ? "Done editing" : "Enable edit";
    editToggle.classList.toggle("active", editMode);
  }

  function selectComponent(slideId, componentId, element) {
    selected = slideId ? {slideId: slideId, componentId: componentId} : null;
    stage.querySelectorAll(".selected-component").forEach(function (node) { node.classList.remove("selected-component"); });
    if (element) element.classList.add("selected-component");
    renderTools();
  }

  function mutateOrder(id, delta) {
    if (!editMode) return;
    var index = state.order.indexOf(id);
    var target = index + delta;
    if (index < 0 || target < 0 || target >= state.order.length) return;
    beginChange();
    state.order.splice(target, 0, state.order.splice(index, 1)[0]);
    currentId = id;
    render();
    persist();
  }

  function toggleHidden(id) {
    if (!editMode) return;
    beginChange();
    var index = state.hidden.indexOf(id);
    if (index >= 0) state.hidden.splice(index, 1);
    else state.hidden.push(id);
    render();
    persist();
  }

  function selectSlide(id) {
    if (state.order.indexOf(id) < 0) return;
    currentId = id;
    selected = null;
    history.replaceState(null, "", "#" + id);
    render();
  }

  function step(delta) {
    var next = Math.max(0, Math.min(state.order.length - 1, currentIndex() + delta));
    selectSlide(state.order[next]);
  }

  function undo() {
    if (!undoBase) return;
    state = copy(undoBase);
    currentId = state.order[0];
    selected = null;
    undoBase = null;
    render();
    persist();
    showToast("Reverted the last edit burst.");
  }

  thumbList.addEventListener("click", function (event) {
    var card = event.target.closest("[data-id]");
    if (!card) return;
    var id = card.getAttribute("data-id");
    var action = event.target.closest("[data-action]");
    if (!action) { selectSlide(id); return; }
    event.preventDefault();
    if (action.getAttribute("data-action") === "move") mutateOrder(id, Number(action.getAttribute("data-delta")));
    else toggleHidden(id);
  });

  document.querySelector("[data-prev]").addEventListener("click", function () { step(-1); });
  document.querySelector("[data-next]").addEventListener("click", function () { step(1); });
  editToggle.addEventListener("click", function () {
    editMode = !editMode;
    selected = null;
    render();
    if (editMode) showToast("Edit mode on — select text or drop an image into the gallery.");
  });
  fullscreenToggle.addEventListener("click", toggleFullscreenPresentation);
  presentationExit.addEventListener("click", exitFullscreenPresentation);
  document.addEventListener("pointermove", function (event) {
    if (event.clientY < 110 && event.clientX > window.innerWidth - 360) revealPresentationExit();
  });
  document.addEventListener("fullscreenchange", function () {
    if (!document.fullscreenElement && document.body.classList.contains("present-only") &&
        !enteredFromPresentationUrl) setPresentationMode(false);
  });
  undoButton.addEventListener("click", undo);

  document.querySelectorAll("[data-font-delta]").forEach(function (button) {
    button.addEventListener("click", function () {
      var component = selectedComponent();
      if (!component || component.kind !== "text") return;
      beginChange();
      var next = Math.max(.7, Math.min(1.5, (component.fontScale || 1) + Number(button.getAttribute("data-font-delta"))));
      updateOverlay(selected.slideId, selected.componentId, "fontScale", Math.round(next * 10) / 10);
      render(); persist();
    });
  });
  document.querySelectorAll("[data-color]").forEach(function (button) {
    button.addEventListener("click", function () {
      var component = selectedComponent();
      if (!component || component.kind !== "text") return;
      beginChange();
      updateOverlay(selected.slideId, selected.componentId, "color", button.getAttribute("data-color"));
      render(); persist();
    });
  });
  document.querySelectorAll("[data-image-delta]").forEach(function (button) {
    button.addEventListener("click", function () {
      var component = selectedComponent();
      if (!component || component.kind !== "image") return;
      beginChange();
      var next = Math.max(.65, Math.min(1.35, (component.imageScale || 1) + Number(button.getAttribute("data-image-delta"))));
      updateOverlay(selected.slideId, selected.componentId, "imageScale", Math.round(next * 20) / 20);
      render(); persist();
    });
  });
  document.querySelector("[data-reset-component]").addEventListener("click", function () {
    if (!selected) return;
    beginChange();
    if (state.overlays[selected.slideId]) delete state.overlays[selected.slideId][selected.componentId];
    cleanOverlay(selected.slideId, selected.componentId);
    render(); persist();
  });

  document.addEventListener("keydown", function (event) {
    if (event.target && event.target.isContentEditable) return;
    if (event.key === "ArrowLeft") step(-1);
    if (event.key === "ArrowRight") step(1);
    if (event.key.toLowerCase() === "f") toggleFullscreenPresentation();
    if (event.key === "Escape" && document.body.classList.contains("present-only")) {
      exitFullscreenPresentation();
    }
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") {
      event.preventDefault(); undo();
    }
  });
  window.addEventListener("hashchange", function () {
    if (!state) return;
    var requested = location.hash.slice(1);
    if (state.order.indexOf(requested) >= 0 && requested !== currentId) {
      currentId = requested;
      selected = null;
      render();
    }
  });

  fetch("api/deck-state", {cache: "no-store"}).then(function (response) {
    if (!response.ok) throw new Error("Could not load the deck");
    return response.json();
  }).then(function (payload) {
    accepted = payload;
    state = copy(payload);
    var requested = location.hash.slice(1);
    currentId = state.order.indexOf(requested) >= 0 ? requested : state.order[0];
    render();
  }).catch(function (error) {
    setStatus("Load failed", "error");
    stage.textContent = error.message;
  });
  if (enteredFromPresentationUrl) revealPresentationExit();
}());

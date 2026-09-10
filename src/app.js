import {createViewport,CANONICAL_SLIDE_WIDTH,CANONICAL_SLIDE_HEIGHT} from './editor/viewport';
import {createTextRegions} from './editor/regions';
import {createTableEditor} from './editor/tables';
import {copy, snapshot, sameSnapshot} from './editor/snapshot';
import {SaveQueue} from './editor/save-queue';
import {textEdit, toggleBold, renderMarkedText, readMarkedText, insertPlainText} from './editor/text';
import {registerTextFit, registerGroupFit, clearFitObservers, trackFitObserver} from './editor/fit';
/* ScientificSlideKit pilot: declarative recipes plus a bundled diagram engine. */
(function () {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";
  var enteredFromPresentationUrl = new URLSearchParams(location.search).get("present") === "1";
  var previewMode = Boolean(window.slidekitPreview);
  if (enteredFromPresentationUrl || previewMode) {
    document.body.classList.add("present-only");
  }
  if (previewMode) document.body.classList.add('preview-only');
  var stage = document.querySelector("[data-stage]");
  var stageWrap = document.querySelector(".stage-wrap");
  var thumbList = document.querySelector("[data-thumb-list]");
  var count = document.querySelector("[data-slide-count]");
  var position = document.querySelector("[data-position]");
  var status = document.querySelector("[data-save-state]");
  var editToggle = document.querySelector("[data-edit-toggle]");
  var fullscreenToggle = document.querySelector("[data-fullscreen-toggle]");
  var presentationExit = document.querySelector("[data-presentation-exit]");
  var undoButton = document.querySelector("[data-undo]");
  var draftButton = document.querySelector("[data-conflict-draft]");
  var draftKey = "slidekit-conflict-draft:" + location.pathname;
  var toast = document.querySelector("[data-toast]");
  var selectedLabel = document.querySelector("[data-selected-component]");
  var state = null;
  var accepted = null;
  var currentId = null;
  var selected = null;
  var editMode = false;
  var undoBase = null;
  var inputTimer = null;
  var toastTimer = null;
  var loadedSlides = new Map();
  var slideRequests = new Map();
  var libraries = new Map();
  var renderGeneration = 0;
  var prefetchTimer = null;
  var focusedThumb = null;
  var focusCreatedTitle = null;
  var focusTextBox = null;
  var creator = previewMode ? null : new window.SlideCreator({
    ready: function() {return Boolean(state && accepted && !saves.pending && !saves.inFlight &&
      sameSnapshot(state, accepted) && status.textContent === 'Saved');},
    currentId: function() {return currentId;},
    created: function(payload) {
      accepted = acceptPayload(payload); state = copy(accepted);
      currentId = payload.loadedSlides[0]; selected = null; undoBase = null;
      editMode = true; focusCreatedTitle = currentId;
      history.replaceState(null, '', '#' + currentId);
      render(); setStatus('Saved', 'saved');
      showToast('Slide created. Type your title; changes save automatically.');
    }
  });
  var previews = previewMode ? null : new window.SlidePreviews(document.querySelector('.filmstrip'), function(id) {
    return ensureSlide(id).then(function(slide) {
      return Object.assign(snapshot(state), {revision:state.revision, sourceRevision:state.sourceRevision,
        runtimeRevision:window.slidekitAssetRevision,
        slideRevisions:{[id]:state.slideRevisions[id]}, slides:{[id]:slide}, loadedSlides:[id]});
    });
  });

  function loadLibrary(name) {
    if (!libraries.has(name)) {
      libraries.set(name, new Promise(function(resolve, reject) {
        var script = document.createElement('script');
        script.src = name + '?v=' + window.slidekitAssetRevision;
        script.onload = resolve;
        script.onerror = function() {libraries.delete(name); script.remove(); reject(new Error('Could not load ' + name));};
        document.head.appendChild(script);
      }));
    }
    return libraries.get(name);
  }

  function acceptPayload(payload) {
    if (payload.runtimeRevision && payload.runtimeRevision !== window.slidekitAssetRevision)
      throw new Error('Renderer changed. Reload the parent deck before showing this preview.');
    // Compact ACKs contain mutable state only. Never reuse stale source specs.
    if (!payload.slides) payload.slides = state.slides;
    if (payload.loadedSlides && state) Object.keys(payload.slides).forEach(function(id) {
      if (!payload.loadedSlides.includes(id) && loadedSlides.get(id) === payload.slideRevisions[id])
        payload.slides[id] = state.slides[id];
    });
    (payload.loadedSlides || (payload.sourceRevision !== (accepted || {}).sourceRevision ? Object.keys(payload.slides) : []))
      .forEach(function(id) { loadedSlides.set(id, payload.slideRevisions[id]); });
    return payload;
  }

  function ensureSlide(id) {
    var revision = state.slideRevisions[id];
    if (loadedSlides.get(id) === revision) return Promise.resolve(slideById(id));
    var displayRevision = state.displayRevision || 'source';
    var key = id + ':' + revision + ':' + displayRevision;
    if (!slideRequests.has(key)) {
      slideRequests.set(key, window.slidekitRequest('api/slides/' + encodeURIComponent(id) + '?revision=' + revision + '&display=' + displayRevision)
        .then(function(r) {if(!r.ok) throw new Error('Slide source changed or unavailable. Reload to continue.'); return r.json();})
        .then(function(slide) {
          if (state.slideRevisions[id] === revision) {
            state.slides[id] = slide; accepted.slides[id] = slide;
            loadedSlides.set(id, revision);
          }
          return slide;
        }).finally(function() {slideRequests.delete(key);}));
    }
    return slideRequests.get(key);
  }

  function prepareSlide(slide) {
    var needed = [];
    if (slide.recipe === 'chart-panels') needed.push(loadLibrary('plotly.min.js'));
    if (slide.recipe === 'mechanism-pipeline') needed.push(loadLibrary('joint-diagram.js'));
    if (slide.recipe === 'vector-geometry') needed.push(loadLibrary('geometry-runtime.js'));
    if (Object.values(slide.components || {}).some(function(c) {return c.render === 'latex';}))
      needed.push(loadLibrary('math-runtime.js'));
    return Promise.all(needed);
  }


  function retainDraft(message, restored) {
    var draft = restored || {message: message, base: snapshot(accepted),
      sourceRevision: accepted.sourceRevision, local: snapshot(state)};
    try { localStorage.setItem(draftKey, JSON.stringify(draft)); } catch (_) {}
    draftButton.hidden = false;
    draftButton.onclick = function () {
      var url = URL.createObjectURL(new Blob([JSON.stringify(draft, null, 2)],
        {type: "application/json"}));
      var link = document.createElement("a");
      link.href = url; link.download = "unsaved-slide-edits.json"; link.click();
      setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    };
  }

  function setStatus(label, kind) {
    status.textContent = label;
    status.className = "save-state " + (kind || "saved");
    if (creator) creator.refresh();
  }

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add("visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toast.classList.remove("visible"); }, 2700);
  }

  var {fitStage,revealPresentationExit,removePresentationQuery,setPresentationMode,exitFullscreenPresentation,toggleFullscreenPresentation} = createViewport({
    stage, stageWrap, presentationExit, fullscreenToggle,
    applyAllTextRegions: function() {applyAllTextRegions();},
    syncTextRegionFrame: function() {syncTextRegionFrame();}, showToast
  });

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
    var box = ((state.textBoxes || {})[slide.id] || {})[componentId];
    if (box) return Object.assign({kind:'text', role:'Text box'}, box);
    var table = insertedTableOwner(slide.id, componentId);
    var source = slide.components[componentId] || (table && table.components[componentId]);
    if (!source) throw new Error("Unknown semantic component " + slide.id + "@" + componentId);
    var overlay = overlayFor(slide.id, componentId, false);
    return Object.assign({}, source, overlay);
  }

  function objectsForSlide(slide) {
    return copy((state.objects || {})[slide.id] || {});
  }

  function updateVisualObject(slideId, objectId, kind, geometry, commit) {
    if (!state.objects) state.objects = {};
    if (!state.objects[slideId]) state.objects[slideId] = {};
    beginChange();
    state.objects[slideId][objectId] = Object.assign({kind: kind}, copy(geometry));
    if (commit) persist();
  }

  function cleanVisualObject(slideId, objectId) {
    if (!state.objects || !state.objects[slideId]) return;
    delete state.objects[slideId][objectId];
    if (!Object.keys(state.objects[slideId]).length) delete state.objects[slideId];
  }

  function cleanOverlay(slideId, componentId) {
    var slideOverlays = state.overlays[slideId];
    if (!slideOverlays) return;
    if (Object.keys(slideOverlays[componentId] || {}).length === 0) delete slideOverlays[componentId];
    if (Object.keys(slideOverlays).length === 0) delete state.overlays[slideId];
  }

  function updateOverlay(slideId, componentId, key, value) {
    var box = ((state.textBoxes || {})[slideId] || {})[componentId];
    if (box) {
      if (value === undefined || value === null) delete box[key];
      else box[key] = value;
      return;
    }
    var source = state.slides[slideId].components[componentId];
    var table = insertedTableOwner(slideId, componentId);
    if (!source && table && table.components[componentId]) {
      if (value === undefined || value === null) delete table.components[componentId][key];
      else table.components[componentId][key] = value;
      return;
    }
    var overlay = overlayFor(slideId, componentId, true);
    if (source[key] === value || value === undefined || value === null) delete overlay[key];
    else overlay[key] = value;
    // Formatting and its exact wording are one conflict domain. Even when
    // wording equals the source, marks may not be persisted without that bind.
    if (Object.prototype.hasOwnProperty.call(overlay, 'marks') && !Object.prototype.hasOwnProperty.call(overlay, 'text'))
      overlay.text = source.text;
    cleanOverlay(slideId, componentId);
  }

  function updateText(slideId, componentId, value) {
    var edit = textEdit(value);
    updateOverlay(slideId, componentId, 'text', edit.text);
    updateOverlay(slideId, componentId, 'marks', edit.marks);
  }

  function insertedTableOwner(slideId, componentId) {
    var matches=Object.keys(state.tables || {}).filter(function(key) {
      return (key===slideId || key.indexOf(slideId+'::table::')===0) && state.tables[key].components[componentId];
    });
    if(matches.length>1) throw new Error('Ambiguous table-owned text '+componentId);
    return matches.length ? state.tables[matches[0]] : null;
  }

  var {tableContexts,selectedTableContext,sourceTableModel,effectiveTable,ensureTable,tableCell,mutateSelectedTable,pasteTableGrid,startTableColumnResize} = createTableEditor({
    getState: function() {return state;}, getSelected: function() {return selected;},
    clearSelection: function() {selected = null;},
    isEditMode: function() {return editMode;}, stage, beginChange, render, persist, effectiveComponent, updateOverlay
  });

  function beginChange() {
    if (!undoBase) undoBase = copy(accepted);
    undoButton.disabled = false;
    setStatus("Saving…", "saving");
  }

  function persist() {
    if (previewMode) return;
    retainDraft('Changes saved on this device; awaiting server acknowledgement.');
    setStatus("Saving…", "saving");
    saves.enqueue();
  }

  var deferredRemoteRender = false;
  var saves = new SaveQueue({
    current: function() {return state;},
    accepted: function() {return accepted;},
    decode: acceptPayload,
    stale: function() {return window.slidekitRuntimeStale();},
    request: function(body) {
      return window.slidekitRequest('api/deck-state', {
        method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)
      }).then(function(response) {return response.json().then(function(payload) {
        return {ok:response.ok,status:response.status,payload:payload};
      });});
    },
    acceptedResult: function(remote, current, clean) {
      // Acknowledging our own edit is not a reason to destroy live editor DOM.
      deferredRemoteRender = deferredRemoteRender || !sameSnapshot(state,current) || accepted.sourceRevision !== remote.sourceRevision;
      state = current; accepted = remote;
      if (clean) {
        undoBase = null;
        if (deferredRemoteRender) {deferredRemoteRender = false; render();}
        else {renderThumbs(); renderTools(); undoButton.disabled = true;}
        setStatus('Saved','saved');
        try {localStorage.removeItem(draftKey);} catch (_) {}
        draftButton.hidden = true;
      } else setStatus('Saving…','saving');
    },
    conflict: function(remote,message) {
      deferredRemoteRender = false;
      retainDraft(message);
      accepted = remote; state = copy(remote); undoBase = null; selected = null;
      render(); setStatus('Conflict · draft retained','error');
      showToast(message + '. Your unsaved changes are available to download.');
    },
    invalid: function(message) {
      retainDraft(message); setStatus('Invalid edit · draft retained','error'); showToast(message);
    },
    retry: function(error) {
      if (error) console.error('deck-state save failed',error);
      setStatus('Offline · retrying','error');
    },
    runtimeChanged: function(error) {
      retainDraft(error.message); setStatus('Renderer updated · reload; draft retained','error');
    },
    schedule: function(callback) {setTimeout(callback,1400);}
  });

  function svgElement(name, attrs) {
    var node = document.createElementNS(SVG_NS, name);
    Object.keys(attrs || {}).forEach(function (key) { node.setAttribute(key, attrs[key]); });
    return node;
  }

  function applyComponentStyle(element, component) {
    if (component.color) element.style.color = component.color;
    if (component.fontScale) element.style.setProperty("--component-scale", component.fontScale);
  }

  function toggleTextBold(slideId, componentId, element) {
    if (!editMode || !element || element.dataset.latexSource !== undefined) return;
    var value = readMarkedText(element), selection = window.getSelection();
    var start = 0, end = value.text.length;
    if (selection.rangeCount && !selection.isCollapsed) {
      var range = selection.getRangeAt(0);
      if (element.contains(range.startContainer) && element.contains(range.endContainer)) {
        var prefix = document.createRange(); prefix.selectNodeContents(element); prefix.setEnd(range.startContainer, range.startOffset);
        start = prefix.toString().length; end = start + range.toString().length;
      }
    }
    if (end <= start) return;
    var formatted = toggleBold(value, start, end, Number(getComputedStyle(element).fontWeight) >= 600);
    beginChange();
    updateText(slideId, componentId, formatted);
    renderMarkedText(element, formatted);
    // Preserve the highlighted range so a second toggle or continued typing
    // operates on the same text, rather than unexpectedly formatting the cell.
    var walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT), node, offset = 0;
    var restored = document.createRange(), started = false;
    while ((node = walker.nextNode())) {
      if (!started && start <= offset + node.length) {restored.setStart(node, start-offset); started = true;}
      if (started && end <= offset + node.length) {restored.setEnd(node, end-offset); break;}
      offset += node.length;
    }
    selection.removeAllRanges(); selection.addRange(restored);
    element.dispatchEvent(new Event('input', {bubbles:true}));
    renderTools();
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
      renderMarkedText(element, component);
    }
    element.setAttribute("data-component-id", componentId);
    element.setAttribute("data-component-kind", "text");
    element.setAttribute("aria-label", component.role || componentId);
    element.contentEditable = editMode && !isLatex ? "true" : "false";
    applyComponentStyle(element, component);
    if (component.hidden) element.classList.add('curator-hidden-component');
    element.addEventListener("click", function (event) {
      if (!editMode) return;
      event.stopPropagation();
      selectComponent(slide.id, componentId, element);
    });
    element.addEventListener("input", function () {
      if (!editMode || isLatex) return;
      var value = readMarkedText(element);
      updateText(slide.id, componentId, value);
      beginChange();
      clearTimeout(inputTimer);
      inputTimer = setTimeout(persist, 260);
    });
    element.addEventListener("paste", function (event) {
      if (!editMode || isLatex) return;
      var raw = event.clipboardData && event.clipboardData.getData("text/plain");
      if (raw === null || raw === undefined) return;
      event.preventDefault();
      if ((raw.includes('\t') || raw.includes('\n')) && pasteTableGrid(slide, componentId, raw)) return;
      insertPlainText(element,raw.replace(/\r\n?/g,'\n'));
    });
    element.addEventListener("keydown", function (event) {
      if (editMode && (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'b') {
        event.preventDefault(); event.stopPropagation();
        toggleTextBold(slide.id,componentId,element); return;
      }
      if (!editMode || event.key !== "Tab" || !element.closest("[data-table-cell]")) return;
      event.preventDefault();
      var cells = Array.from(element.closest('[data-native-table]').querySelectorAll("[data-table-cell] .semantic-component"));
      var index = cells.indexOf(element);
      var next = cells[index + (event.shiftKey ? -1 : 1)];
      if (!next) next = cells[event.shiftKey ? cells.length - 1 : 0];
      next.focus();
      next.click();
    });
    element.addEventListener('beforeinput', function(event) {
      if (editMode && !isLatex && ['insertParagraph','insertLineBreak'].includes(event.inputType)) {
        event.preventDefault(); insertPlainText(element,'\n'); return;
      }
      if (event.inputType === 'formatBold') {
        event.preventDefault(); toggleTextBold(slide.id,componentId,element);
      }
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
    bindTextRegion(slide, componentId, element, element, {minSize: 10});
    return element;
  }

  var {bindTextRegion,applyAllTextRegions,syncTextRegionFrame,removeTextRegionFrame,clearTextRegions} = createTextRegions({
    getComponent: function(sid,cid) {return cid ? effectiveComponent(state.slides[sid],cid) : null;},
    getSelected: function() {return selected;}, isEditMode: function() {return editMode;},
    beginChange,persist,updateOverlay,
    resizeChart: function(host) {
      if(host._fullLayout && window.Plotly && (host.layout.width!==host.clientWidth || host.layout.height!==host.clientHeight))
        window.Plotly.relayout(host,{width:host.clientWidth,height:host.clientHeight});
    }
  });

  function effectiveHeadline(slide) {
    return effectiveComponent(slide, slide.headline).text;
  }

  document.querySelector("[data-notes-toggle]").addEventListener("click", function () {
    var slide = currentSlide();
    var host = document.querySelector("[data-notes-content]");
    host.textContent = "";
    ["facts", "notes", "narrative"].forEach(function (key) {
      if (!slide[key]) return;
      var heading = document.createElement("h2"); heading.textContent = key;
      var text = document.createElement("div"); text.className = "notes-text";
      text.textContent = typeof slide[key] === "string" ? slide[key] : JSON.stringify(slide[key], null, 2);
      host.append(heading, text);
    });
    if (!host.childNodes.length) host.textContent = "No private notes for this slide.";
    document.querySelector("[data-notes-dialog]").showModal();
  });

  function slideShell(slide) {
    var canvas = document.createElement("article");
    canvas.className = "slide-canvas recipe-" + slide.recipe;
    if (slide.recipe === 'section-divider' && slide.data.centered) canvas.classList.add('centered-section');
    canvas.style.setProperty("--accent", (slide.theme||{}).accent||"#2f6fed");
    canvas.setAttribute("data-slide-id", slide.id);
    canvas.setAttribute("data-canonical-width", String(CANONICAL_SLIDE_WIDTH));
    canvas.setAttribute("data-canonical-height", String(CANONICAL_SLIDE_HEIGHT));
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
    if (slide.recipe === 'section-divider' && slide.data.centered) return;
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
    window.slidekitRequest("api/assets", {method: "POST", headers: {"Content-Type": file.type, "X-File-Name": file.name}, body: file})
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
    if(component.hidden) cell.classList.add('curator-hidden-component');
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
      bindTextRegion(slide, component.caption, caption, captionFrame, {
        alwaysFit: true,
        fitMode: "gallery-caption-region",
        minSize: 12
      });
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
    bindTextRegion: bindTextRegion,
    selectBoundedComponent: selectComponent,
    galleryImage: galleryImage,
    effectiveComponent: effectiveComponent,
    sourceRevision: function(slideId) { return state.slideRevisions[slideId]; },
    effectiveTable: effectiveTable,
    startTableColumnResize: startTableColumnResize,
    fitTextInRegion: registerTextFit,
    fitGroupInRegion: registerGroupFit,
    isEditMode: function () { return editMode; },
    isSlideHidden: function(id) {return state.hidden.indexOf(id)>=0;},
    orderOfSlide: function(id) {return state.order.indexOf(id);},
    setSlidesHidden: function(ids,hidden) {
      if(!editMode) return;
      beginChange();
      ids.forEach(function(id) {
        if(!state.slides[id]) throw new Error('Unknown index destination '+id);
        var index=state.hidden.indexOf(id);
        if(hidden && index<0) state.hidden.push(id);
        if(!hidden && index>=0) state.hidden.splice(index,1);
      });
      render();persist();
    },
    objectsForSlide: objectsForSlide,
    selectedObjectId: function (slide) {
      return selected && selected.visualObject && selected.slideId === slide.id ? selected.objectId : null;
    },
    selectVisualObject: function (slideId, objectId, objectKind) {
      selected = {slideId: slideId, objectId: objectId, objectKind: objectKind, visualObject: true};
      stage.querySelectorAll(".selected-component").forEach(function (node) {
        node.classList.remove("selected-component");
      });
      removeTextRegionFrame();
      renderTools();
    },
    updateVisualObject: updateVisualObject,
    saveChartLayout: function (slideId, componentId, value) {
      beginChange();
      updateOverlay(slideId, componentId, "chartLayout", value);
      persist();
    }
  });

  function clearStage(message) {
    clearFitObservers();
    removeTextRegionFrame();
    clearTextRegions();
    stage.querySelectorAll(".native-chart").forEach(function (chart) {
      window.disposeScientificChart(chart);
    });
    stage.textContent = message;
  }

  function renderStage() {
    // A save acknowledgment must not steal the caret from an active editor.
    var active=document.activeElement, caret=null, selection=getSelection();
    if (editMode && active && active.isContentEditable && stage.contains(active) && selection.rangeCount) {
      var range=selection.getRangeAt(0);
      if(active.contains(range.startContainer) && active.contains(range.endContainer)) {
        var prefix=document.createRange();prefix.selectNodeContents(active);prefix.setEnd(range.startContainer,range.startOffset);
        caret={slideId:active.closest('.slide-canvas').dataset.slideId,id:active.dataset.componentId,text:active.textContent,start:prefix.toString().length,length:range.toString().length};
      }
    }
    var index = currentIndex();
    currentId = state.order[index];
    var slide = currentSlide();
    clearStage('');
    var canvas = slideShell(slide);
    renderRecipe[slide.recipe](canvas, slide);
    addFooter(canvas, slide);
    renderRecipe.annotations(canvas,slide);
    Object.keys((state.textBoxes || {})[slide.id] || {}).forEach(function(id) {
      var text = editableText(slide,id,'div','slide-annotation-text');
      canvas.appendChild(text);
      bindTextRegion(slide,id,text,text,{alwaysFit:true});
    });
    stage.appendChild(canvas);
    fitStage();
    stage.classList.toggle("edit-mode", editMode);
    applyAllTextRegions();
    if(caret && caret.slideId===currentId) {
      var replacement=stage.querySelector('[data-component-id="'+caret.id+'"]');
      if(replacement && replacement.isContentEditable && replacement.textContent===caret.text) {
        replacement.focus();
        var walker=document.createTreeWalker(replacement,NodeFilter.SHOW_TEXT),node,offset=0,restored=document.createRange(),started=false;
        while((node=walker.nextNode())) {
          if(!started && caret.start<=offset+node.length) {restored.setStart(node,caret.start-offset);started=true;}
          if(started && caret.start+caret.length<=offset+node.length) {restored.setEnd(node,caret.start+caret.length-offset);break;}
          offset+=node.length;
        }
        if(started) {selection.removeAllRanges();selection.addRange(restored);}
      }
    }
    if (window.ResizeObserver) {
      var canvasObserver = new ResizeObserver(function () {
        requestAnimationFrame(function () {
          if (!canvas.isConnected) return;
          applyAllTextRegions();
          syncTextRegionFrame();
        });
      });
      canvasObserver.observe(canvas);
      trackFitObserver(canvasObserver);
    }
    position.textContent = (index + 1) + " / " + state.order.length;
    document.querySelector('[data-layouts-link]').href = 'catalog.html#' + currentId;
    document.querySelector("[data-prev]").disabled = index === 0;
    document.querySelector("[data-next]").disabled = index === state.order.length - 1;
    if (selected && !selected.visualObject && selected.slideId === currentId) {
      var element = stage.querySelector('[data-component-id="' + selected.componentId + '"]');
      if (element) {
        element.classList.add("selected-component");
        selected.tableCell = tableCell(slide, selected.componentId);
        if (!selected.tableCell) delete selected.tableCell;
      }
    }
    requestAnimationFrame(syncTextRegionFrame);
    if (focusCreatedTitle === currentId) {
      focusCreatedTitle = null;
      var title = canvas.querySelector('[data-component-id="' + slide.headline + '"]');
      title.focus(); selectComponent(slide.id, slide.headline, title);
      var range = document.createRange(); range.selectNodeContents(title);
      var selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
    }
  }

  function renderThumbs() {
    if (previewMode) return;
    var existing = new Map(Array.from(thumbList.children).map(function(card) {return [card.dataset.id,card];}));
    count.textContent = String(state.order.length);
    state.order.forEach(function (id, index) {
      var slide = slideById(id);
      var key = JSON.stringify([state.slideRevisions[id],state.overlays[id],(state.tables||{})[id],
        (state.objects||{})[id],(state.textBoxes||{})[id],state.hidden.includes(id)]);
      var retained = existing.get(id);
      if (retained && retained.dataset.previewKey === key) {
        retained.classList.toggle('current', id === currentId);
        retained.querySelector('.thumb-index').textContent = String(index + 1).padStart(2,'0');
        retained.querySelectorAll('[data-action="move"]').forEach(function(button) {
          var target = index + Number(button.dataset.delta);
          button.disabled = target < 0 || target >= state.order.length;
        });
        if (thumbList.children[index] !== retained) thumbList.insertBefore(retained,thumbList.children[index] || null);
        existing.delete(id);
        return;
      }
      if (retained) {retained.remove(); existing.delete(id);}
      var card = document.createElement("article");
      card.dataset.previewKey = key;
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
      art.style.setProperty("--thumb-accent", (slide.theme||{}).accent||"#2f6fed");
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
       [state.hidden.indexOf(id) >= 0 ? "Show" : "Hide", "visibility", null,
        state.hidden.indexOf(id) >= 0 ? "Show slide" : "Hide slide"]].forEach(function (item) {
        var button = document.createElement("button");
        button.className = "thumb-action " + item[1];
        button.type = "button";
        button.textContent = item[0];
        button.setAttribute("aria-label", item[3]);
        button.title = item[3];
        if (item[1] === 'move') button.disabled = index + item[2] < 0 || index + item[2] >= state.order.length;
        button.setAttribute("data-action", item[1]);
        if (item[2] !== null) button.setAttribute("data-delta", item[2]);
        actions.appendChild(button);
      });
      inner.appendChild(actions);
      card.appendChild(inner);
      thumbList.insertBefore(card,thumbList.children[index] || null);
    });
    existing.forEach(function(card) {card.remove();});
    // Follow navigation/reload, never reset the curator's manual rail browsing
    // during saves, text edits, or thumbnail arrival.
    if (focusedThumb !== currentId) {
      focusedThumb = currentId;
      var focused = Array.from(thumbList.children).find(function(card) {return card.dataset.id === currentId;});
      if (focused) focused.scrollIntoView({block:'nearest',inline:'nearest',behavior:'instant'});
    }
    previews.sync();
  }

  function selectedComponent() {
    if (!selected || selected.visualObject || !state.slides[selected.slideId]) return null;
    return effectiveComponent(state.slides[selected.slideId], selected.componentId);
  }

  function renderTools() {
    var component = selectedComponent();
    var textSelected = editMode && component && component.kind === "text";
    var imageSelected = editMode && component && component.kind === "image";
    var boldButton = document.querySelector('[data-bold]');
    boldButton.disabled = !textSelected || component.render === 'latex';
    boldButton.setAttribute('aria-pressed', String(Boolean(textSelected && (component.marks || []).some(function(mark) {return mark.bold;}))));
    document.querySelectorAll("[data-font-delta], [data-color]").forEach(function (button) { button.disabled = !textSelected; });
    document.querySelectorAll("[data-image-delta]").forEach(function (button) { button.disabled = !imageSelected; });
    var objectSelected = Boolean(editMode && selected && selected.visualObject);
    document.querySelector("[data-reset-component]").disabled = !(editMode && (component || objectSelected)) || Boolean(selected && ((state.textBoxes || {})[selected.slideId] || {})[selected.componentId]);
    var hideButton=document.querySelector('[data-hide-component]');
    hideButton.disabled=!(editMode && component);
    hideButton.textContent=component && component.hidden ? 'Show' : 'Hide';
    var tableSelected = Boolean(editMode && selected && selected.tableCell);
    document.querySelectorAll("[data-table-action]").forEach(function (button) {
      var action = button.getAttribute("data-table-action");
      var cell = selected && selected.tableCell;
      var disabled = !tableSelected;
      if (cell && action.indexOf("row-") === 0 && cell.header) disabled = true;
      if (cell && action === "column-delete" && cell.columnIndex === 0) disabled = true;
      if (cell && (action === "column-left" || action === "column-right") && cell.columnIndex === 0) disabled = true;
      button.disabled = disabled;
    });
    document.querySelector("[data-table-tools]").hidden = !tableSelected;
    selectedLabel.textContent = component ? selected.slideId + " @ " + selected.componentId +
      (textSelected ? " · drag top edge · resize corner" : "") :
      (objectSelected ? selected.slideId + " @ " + selected.objectId + " · " + selected.objectKind :
        "Select a component or visual object in edit mode");
  }

  function render() {
    var generation = ++renderGeneration;
    if (previews) previews.pause();
    clearTimeout(prefetchTimer);
    // Never leave an old slide editable while a new route is loading.
    var canvas = stage.querySelector('.slide-canvas');
    if (!canvas || canvas.dataset.slideId !== currentId || loadedSlides.get(currentId) !== state.slideRevisions[currentId])
      clearStage('Loading slide…');
    renderThumbs();
    ensureSlide(currentId).then(prepareSlide).then(function() {
      if (generation !== renderGeneration) return;
      renderStage(); renderTools();
      if (focusTextBox) {
        var added = stage.querySelector('[data-component-id="'+focusTextBox+'"]');
        focusTextBox = null;
        if (added) {
          added.focus(); added.click();
          var range=document.createRange(); range.selectNodeContents(added);
          var selection=getSelection(); selection.removeAllRanges(); selection.addRange(range);
        }
      }
      // Give the main slide its first useful paint before background previews.
      var readyDeadline = performance.now() + 18000;
      function afterUsefulPaint() {
        if (generation !== renderGeneration) return;
        var ready = document.fonts.status === 'loaded' &&
          Array.from(stage.querySelectorAll('img')).every(function(img) {return img.complete && img.naturalWidth;}) &&
          Array.from(stage.querySelectorAll('.native-chart')).every(function(chart) {return chart.dataset.chartReady === 'true';});
        if (!ready) {if(performance.now() < readyDeadline) setTimeout(afterUsefulPaint,100); return;}
        if (previewMode) parent.postMessage({type:'slidekit-preview-ready', revision:state.sourceRevision},location.origin);
        else {creator.warm(); previews.start();}
      }
      requestAnimationFrame(function() {requestAnimationFrame(afterUsefulPaint);});
      // Only the next source, only after paint, and never large image pages.
      if (previewMode) return;
      prefetchTimer = setTimeout(function() {
        var next = state.order[currentIndex() + 1];
        if (next && !(navigator.connection && navigator.connection.saveData)) ensureSlide(next).catch(function() {});
      }, 1200);
    }).catch(function(error) {
      if (generation !== renderGeneration) return;
      stage.textContent = error.message;
      setStatus('Slide unavailable · reload', 'error');
    });
    undoButton.disabled = !undoBase;
    editToggle.textContent = editMode ? "Done editing" : "Enable edit";
    editToggle.classList.toggle("active", editMode);
    document.querySelector('[data-add-text]').hidden = !editMode;
  }

  function addTextBox(x, y) {
    if (!editMode || !state || loadedSlides.get(currentId) !== state.slideRevisions[currentId]) return;
    beginChange();
    var id='text-box-'+crypto.randomUUID();
    if (!state.textBoxes) state.textBoxes={};
    if (!state.textBoxes[currentId]) state.textBoxes[currentId]={};
    state.textBoxes[currentId][id]={text:'Type your text', region:{
      x:Math.max(24,Math.min(1376,x)), y:Math.max(24,Math.min(896,y)), width:520, height:160}};
    focusTextBox=id;
    render(); persist();
  }

  document.querySelector('[data-add-text]').addEventListener('click',function() {addTextBox(700,450);});
  stage.addEventListener('dblclick',function(event) {
    if (!editMode || event.target.closest('[data-component-id], [data-visual-object-id], button, input, svg, canvas, .native-chart, [data-native-table], .text-region-frame')) return;
    var canvas=event.target.closest('.slide-canvas');
    if (!canvas) return;
    event.preventDefault();
    var box=canvas.getBoundingClientRect();
    addTextBox((event.clientX-box.left)*1920/box.width,(event.clientY-box.top)*1080/box.height);
  });

  function selectComponent(slideId, componentId, element) {
    selected = slideId ? {slideId: slideId, componentId: componentId} : null;
    stage.querySelectorAll(".selected-visual-object").forEach(function (node) {
      node.classList.remove("selected-visual-object");
    });
    stage.querySelectorAll(".accessibility-object-frame, .accessibility-line-controls").forEach(function (node) {
      node.hidden = true;
    });
    if (selected && element) {
      var cell = element.closest("[data-table-cell]");
      if (cell) {
        selected.tableCell = {
          tableKey:cell.closest('[data-native-table]').dataset.nativeTable,
          header: cell.dataset.tableRowId === "table-header",
          rowIndex: Number(cell.dataset.tableRowIndex),
          columnIndex: Number(cell.dataset.tableColumnIndex),
          rowId: cell.dataset.tableRowId,
          columnId: cell.dataset.tableColumnId
        };
      }
    }
    stage.querySelectorAll(".selected-component").forEach(function (node) { node.classList.remove("selected-component"); });
    if (element) element.classList.add("selected-component");
    renderTools();
    requestAnimationFrame(syncTextRegionFrame);
  }

  function mutateOrder(id, delta) {
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
    if (state.order.indexOf(id) < 0) return;
    beginChange();
    var index = state.hidden.indexOf(id);
    if (index >= 0) state.hidden.splice(index, 1);
    else state.hidden.push(id);
    render();
    persist();
    showToast(index < 0 ? 'Slide hidden.' : 'Slide shown.');
  }

  function selectSlide(id) {
    if (state.order.indexOf(id) < 0) return;
    // Selection is navigation, not a command to destroy/recreate the chart.
    if (id === currentId) return;
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
    if (editMode) showToast("Edit mode on — select text, tables, shapes, lines, or gallery images.");
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
  document.querySelector('[data-bold]').addEventListener('pointerdown', function(event) {event.preventDefault();});
  document.querySelector('[data-bold]').addEventListener('click', function() {
    if (!selected) return;
    toggleTextBold(selected.slideId, selected.componentId,
      stage.querySelector('[data-component-id="' + selected.componentId + '"]'));
  });

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
    if (selected.visualObject) {
      cleanVisualObject(selected.slideId, selected.objectId);
    } else {
      if (state.overlays[selected.slideId]) delete state.overlays[selected.slideId][selected.componentId];
      cleanOverlay(selected.slideId, selected.componentId);
    }
    render(); persist();
  });
  document.querySelector('[data-hide-component]').addEventListener('click',function(){
    var component=selectedComponent();if(!editMode || !component)return;
    beginChange();updateOverlay(selected.slideId,selected.componentId,'hidden',!component.hidden);
    render();persist();
  });
  document.querySelectorAll("[data-table-action]").forEach(function (button) {
    button.addEventListener("click", function () {
      mutateSelectedTable(button.getAttribute("data-table-action"));
    });
  });

  document.addEventListener("keydown", function (event) {
    if (document.querySelector('dialog[open]')) return;
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
  function resolveRoute(requested) {
    if(state.order.indexOf(requested)>=0)return requested;
    for(var id of state.order) {
      var route=(state.slides[id].routes||[]).find(function(item){return item.id===requested;});
      if(route) {
        localStorage.setItem('online-slide.chart-views.'+id,JSON.stringify(route.selection));
        return id;
      }
    }
    return null;
  }
  window.addEventListener("hashchange", function () {
    if (!state) return;
    var requested = resolveRoute(location.hash.slice(1));
    if (requested) {
      currentId = requested;
      selected = null;
      render();
    }
  });

  if (window.ResizeObserver) {
    new ResizeObserver(fitStage).observe(stageWrap);
  } else {
    window.addEventListener("resize", fitStage);
  }

  window.addEventListener('beforeunload', function() {
    if (state && accepted && !sameSnapshot(state, accepted)) retainDraft('Unsaved local changes retained.');
  });
  window.addEventListener('slidekit-runtime-changed', function() {
    if (state && accepted && (saves.pending || saves.inFlight || !sameSnapshot(state, accepted))) {
      retainDraft('Renderer updated. Reload after downloading unsaved edits.');
      setStatus('Renderer updated · reload; draft retained', 'error');
      showToast('Renderer updated. Your unsaved edits are retained on this device; download them before reloading.');
    } else if (!previewMode) location.reload();
  });
  function checkRuntime() {
    if (!previewMode && !document.hidden)
      window.slidekitRequest('api/runtime', {cache:'no-store'}).catch(function() {});
  }
  window.addEventListener('focus', checkRuntime);
  if (!previewMode) setInterval(checkRuntime, 30000);
  window.slidekitBoot.then(function (payload) {
    accepted = acceptPayload(payload);
    state = copy(payload);
    var requested = resolveRoute(location.hash.slice(1));
    currentId = requested || state.order[0];
    render();
    if (previewMode) {
      // A bounded preview host can render many payloads without another page
      // load. Generation fencing in render() rejects late library work.
      window.addEventListener('message', function(event) {
        if (event.origin !== location.origin || event.source !== parent || event.data?.type !== 'slidekit-preview-update') return;
        accepted = acceptPayload(event.data.payload); state = copy(accepted);
        currentId = state.order[0]; selected = null; render();
      });
      parent.postMessage({type:'slidekit-preview-initialized', revision:state.sourceRevision}, location.origin);
      return;
    }
    creator.refresh();
    var starter = new URLSearchParams(location.search).get('new');
    if (starter) {
      var cleanUrl = new URL(location.href); cleanUrl.searchParams.delete('new');
      history.replaceState(null, '', cleanUrl);
      creator.show(starter);
    }
    try {
      var draft = JSON.parse(localStorage.getItem(draftKey));
      if (draft) retainDraft(draft.message, draft);
    } catch (_) {}
  }).catch(function (error) {
    if (window.slidekitRuntimeStale() && !previewMode && !state) {location.reload(); return;}
    setStatus("Load failed", "error");
    stage.textContent = error.message;
  });
  if (enteredFromPresentationUrl) revealPresentationExit();
}());

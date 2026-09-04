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
  var textRegionBindings = new Map();
  var textRegionFrame = null;
  var regionGesture = null;
  var tableColumnGesture = null;

  var CANONICAL_SLIDE_WIDTH = 1920;
  var CANONICAL_SLIDE_HEIGHT = 1080;

  function copy(value) { return JSON.parse(JSON.stringify(value)); }

  function snapshot(value) {
    return {
      schema: value.schema,
      order: value.order.slice(),
      hidden: value.hidden.slice(),
      overlays: copy(value.overlays),
      tables: copy(value.tables || {}),
      objects: copy(value.objects || {})
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
    var table = (state.tables || {})[slide.id];
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
    var source = state.slides[slideId].components[componentId];
    var table = (state.tables || {})[slideId];
    if (!source && table && table.components[componentId]) {
      if (value === undefined || value === null) delete table.components[componentId][key];
      else table.components[componentId][key] = value;
      return;
    }
    var overlay = overlayFor(slideId, componentId, true);
    if (source[key] === value || value === undefined || value === null) delete overlay[key];
    else overlay[key] = value;
    cleanOverlay(slideId, componentId);
  }

  function sourceTableModel(slide) {
    return {
      columns: slide.data.columns.map(function (componentId, index) {
        return {id: componentId, label: componentId, width: index === 0 ? 1.5 : 1};
      }),
      rows: slide.data.rows.map(function (row) {
        return {
          id: row.label,
          label: row.label,
          cells: row.cells.slice(),
          best: Number.isInteger(row.best) ? row.cells[row.best] : null,
          globalBest: Number.isInteger(row.globalBest) ? row.cells[row.globalBest] : null
        };
      }),
      components: {}
    };
  }

  function effectiveTable(slide) {
    return (state.tables || {})[slide.id] || sourceTableModel(slide);
  }

  function ensureTable(slide) {
    if (!state.tables) state.tables = {};
    if (!state.tables[slide.id]) state.tables[slide.id] = sourceTableModel(slide);
    return state.tables[slide.id];
  }

  function tableToken() {
    var random = Math.random().toString(36).slice(2, 8);
    return Date.now().toString(36) + "-" + random;
  }

  function insertedTableText(table, prefix, value, role) {
    var id = prefix + "-" + tableToken();
    table.components[id] = {kind: "text", text: value, role: role};
    return id;
  }

  function retireTableComponent(table, componentId) {
    if (table.components[componentId]) delete table.components[componentId];
  }

  function tableCell(slide, componentId) {
    if (!slide || slide.recipe !== "evidence-table") return null;
    var table = effectiveTable(slide);
    for (var columnIndex = 0; columnIndex < table.columns.length; columnIndex += 1) {
      if (table.columns[columnIndex].label === componentId) {
        return {header: true, rowIndex: -1, columnIndex: columnIndex,
          rowId: "table-header", columnId: table.columns[columnIndex].id};
      }
    }
    for (var rowIndex = 0; rowIndex < table.rows.length; rowIndex += 1) {
      var row = table.rows[rowIndex];
      if (row.label === componentId) {
        return {header: false, rowIndex: rowIndex, columnIndex: 0,
          rowId: row.id, columnId: table.columns[0].id};
      }
      var cellIndex = row.cells.indexOf(componentId);
      if (cellIndex >= 0) {
        return {header: false, rowIndex: rowIndex, columnIndex: cellIndex + 1,
          rowId: row.id, columnId: table.columns[cellIndex + 1].id};
      }
    }
    return null;
  }

  function addTableRow(slide, afterIndex) {
    var table = ensureTable(slide);
    var token = tableToken();
    var label = "table-row-" + token;
    table.components[label] = {kind: "text", text: "New row", role: "table-row-label"};
    var cells = table.columns.slice(1).map(function () {
      return insertedTableText(table, "table-cell", "—", "table-value");
    });
    var row = {id: label, label: label, cells: cells, best: null, globalBest: null};
    table.rows.splice(Math.max(0, Math.min(table.rows.length, afterIndex + 1)), 0, row);
    return row;
  }

  function addTableColumn(slide, afterIndex) {
    var table = ensureTable(slide);
    var label = insertedTableText(table, "table-column", "New column", "table-heading");
    var insertAt = Math.max(1, Math.min(table.columns.length, afterIndex + 1));
    table.columns.splice(insertAt, 0, {id: label, label: label, width: 1});
    table.rows.forEach(function (row) {
      row.cells.splice(insertAt - 1, 0,
        insertedTableText(table, "table-cell", "—", "table-value"));
    });
    return insertAt;
  }

  function mutateSelectedTable(action) {
    if (!selected || !selected.tableCell) return;
    var slide = state.slides[selected.slideId];
    if (!slide || slide.recipe !== "evidence-table") return;
    var table = ensureTable(slide);
    var cell = selected.tableCell;
    beginChange();
    if (action === "table-reset") {
      delete state.tables[slide.id];
      selected = null;
    } else if (action === "row-add") {
      var row = addTableRow(slide, cell.rowIndex < 0 ? table.rows.length - 1 : cell.rowIndex);
      selected.componentId = row.label;
    } else if (action === "row-delete" && cell.rowIndex >= 0 && table.rows.length > 1) {
      var removedRow = table.rows.splice(cell.rowIndex, 1)[0];
      retireTableComponent(table, removedRow.label);
      removedRow.cells.forEach(function (componentId) {
        retireTableComponent(table, componentId);
      });
      selected = null;
    } else if ((action === "row-up" || action === "row-down") && cell.rowIndex >= 0) {
      var rowTarget = cell.rowIndex + (action === "row-up" ? -1 : 1);
      if (rowTarget >= 0 && rowTarget < table.rows.length) {
        table.rows.splice(rowTarget, 0, table.rows.splice(cell.rowIndex, 1)[0]);
      }
    } else if (action === "column-add") {
      var columnIndex = addTableColumn(slide, cell.columnIndex);
      selected.componentId = table.columns[columnIndex].label;
    } else if (action === "column-delete" && cell.columnIndex > 0 && table.columns.length > 2) {
      var removed = table.columns.splice(cell.columnIndex, 1)[0];
      table.rows.forEach(function (rowItem) {
        var removedCell = rowItem.cells.splice(cell.columnIndex - 1, 1)[0];
        if (rowItem.best === removedCell) rowItem.best = null;
        if (rowItem.globalBest === removedCell) rowItem.globalBest = null;
        retireTableComponent(table, removedCell);
      });
      retireTableComponent(table, removed.label);
      selected = null;
    } else if ((action === "column-left" || action === "column-right") && cell.columnIndex > 0) {
      var columnTarget = cell.columnIndex + (action === "column-left" ? -1 : 1);
      if (columnTarget > 0 && columnTarget < table.columns.length) {
        table.columns.splice(columnTarget, 0, table.columns.splice(cell.columnIndex, 1)[0]);
        table.rows.forEach(function (rowItem) {
          rowItem.cells.splice(columnTarget - 1, 0,
            rowItem.cells.splice(cell.columnIndex - 1, 1)[0]);
        });
      }
    }
    render();
    persist();
  }

  function setTableText(slide, table, componentId, value) {
    if (table.components[componentId]) table.components[componentId].text = value;
    else updateOverlay(slide.id, componentId, "text", value);
  }

  function pasteTableGrid(slide, componentId, raw) {
    var start = tableCell(slide, componentId);
    if (!start) return false;
    var values = raw.replace(/\r/g, "").split("\n").filter(function (line, index, rows) {
      return line.length || index < rows.length - 1;
    }).map(function (line) { return line.split("\t"); });
    if (!values.length || (values.length === 1 && values[0].length === 1)) return false;
    var table = ensureTable(slide);
    beginChange();
    while (start.columnIndex + Math.max.apply(null, values.map(function (row) { return row.length; })) > table.columns.length) {
      addTableColumn(slide, table.columns.length - 1);
    }
    if (!start.header) {
      while (start.rowIndex + values.length > table.rows.length) addTableRow(slide, table.rows.length - 1);
    }
    values.forEach(function (valuesRow, rowOffset) {
      valuesRow.forEach(function (value, columnOffset) {
        var columnIndex = start.columnIndex + columnOffset;
        var targetId;
        if (start.header && rowOffset === 0) {
          targetId = table.columns[columnIndex].label;
        } else {
          var rowIndex = start.header ? rowOffset - 1 : start.rowIndex + rowOffset;
          if (rowIndex < 0) return;
          targetId = columnIndex === 0 ? table.rows[rowIndex].label : table.rows[rowIndex].cells[columnIndex - 1];
        }
        setTableText(slide, table, targetId, value.trim());
      });
    });
    render();
    persist();
    return true;
  }

  function startTableColumnResize(slide, columnId, event) {
    if (!editMode) return;
    event.preventDefault();
    event.stopPropagation();
    var table = ensureTable(slide);
    var index = table.columns.findIndex(function (column) { return column.id === columnId; });
    if (index < 0) return;
    beginChange();
    var body = event.target.closest(".table-body").getBoundingClientRect();
    tableColumnGesture = {
      slide: slide,
      table: table,
      index: index,
      startX: event.clientX,
      startWidth: table.columns[index].width,
      bodyWidth: body.width,
      total: table.columns.reduce(function (sum, column) { return sum + column.width; }, 0)
    };
    document.body.classList.add("resizing-table-column");
    document.addEventListener("pointermove", moveTableColumnResize);
    document.addEventListener("pointerup", finishTableColumnResize, {once: true});
    document.addEventListener("pointercancel", finishTableColumnResize, {once: true});
  }

  function moveTableColumnResize(event) {
    if (!tableColumnGesture) return;
    event.preventDefault();
    var gesture = tableColumnGesture;
    var delta = (event.clientX - gesture.startX) / gesture.bodyWidth * gesture.total;
    gesture.table.columns[gesture.index].width = Math.max(.35, Math.min(4, gesture.startWidth + delta));
    var tableElement = stage.querySelector(".evidence-table");
    if (!tableElement) return;
    var total = gesture.table.columns.reduce(function (sum, column) { return sum + column.width; }, 0);
    gesture.table.columns.forEach(function (column) {
      var col = tableElement.querySelector('col[data-table-column-id="' + column.id + '"]');
      if (col) col.style.width = (column.width / total * 100).toFixed(3) + "%";
    });
  }

  function finishTableColumnResize() {
    document.removeEventListener("pointermove", moveTableColumnResize);
    document.removeEventListener("pointerup", finishTableColumnResize);
    document.removeEventListener("pointercancel", finishTableColumnResize);
    document.body.classList.remove("resizing-table-column");
    if (!tableColumnGesture) return;
    tableColumnGesture = null;
    render();
    persist();
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
    }).catch(function (error) {
      console.error("deck-state save failed", error);
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
    element.addEventListener("paste", function (event) {
      if (!editMode || isLatex) return;
      var raw = event.clipboardData && event.clipboardData.getData("text/plain");
      if (!raw || (raw.indexOf("\t") < 0 && raw.indexOf("\n") < 0)) return;
      if (pasteTableGrid(slide, componentId, raw)) event.preventDefault();
    });
    element.addEventListener("keydown", function (event) {
      if (!editMode || event.key !== "Tab" || !element.closest("[data-table-cell]")) return;
      event.preventDefault();
      var cells = Array.from(stage.querySelectorAll("[data-table-cell] .semantic-component"));
      var index = cells.indexOf(element);
      var next = cells[index + (event.shiftKey ? -1 : 1)];
      if (!next) next = cells[event.shiftKey ? cells.length - 1 : 0];
      next.focus();
      next.click();
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
      return contained && element.scrollWidth <= element.clientWidth + tolerance &&
        element.scrollHeight <= element.clientHeight + tolerance && leaves().every(function (leaf) {
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
      element.scrollWidth > element.clientWidth + tolerance ||
      element.scrollHeight > element.clientHeight + tolerance ||
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

  function textRegionKey(slideId, componentId) {
    return slideId + "@" + componentId;
  }

  function bindTextRegion(slide, componentId, element, host, options) {
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

  function canvasScale(canvas) {
    return {
      x: canvas.clientWidth / CANONICAL_SLIDE_WIDTH,
      y: canvas.clientHeight / CANONICAL_SLIDE_HEIGHT
    };
  }

  function ensureTextRegionFit(binding) {
    if (binding.fitRegistered) return;
    binding.fitRegistered = true;
    registerTextFit(binding.element, binding.host, {
      mode: binding.fitMode,
      minSize: binding.minSize
    });
  }

  function applyTextRegion(binding) {
    var canvas = binding.host.closest(".slide-canvas");
    if (!canvas) return;
    var component = effectiveComponent(state.slides[binding.slideId], binding.componentId);
    var region = component.region;
    if (!region) {
      if (binding.alwaysFit) ensureTextRegionFit(binding);
      return;
    }
    var scale = canvasScale(canvas);
    binding.host.style.translate = (region.x * scale.x).toFixed(2) + "px " +
      (region.y * scale.y).toFixed(2) + "px";
    binding.host.style.width = (region.width * scale.x).toFixed(2) + "px";
    binding.host.style.height = (region.height * scale.y).toFixed(2) + "px";
    binding.host.classList.add("text-region-bounded");
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
    if (!selected || !editMode) return null;
    var component = selectedComponent();
    if (!component || component.kind !== "text") return null;
    return textRegionBindings.get(textRegionKey(selected.slideId, selected.componentId)) || null;
  }

  function removeTextRegionFrame() {
    if (textRegionFrame) textRegionFrame.remove();
    textRegionFrame = null;
  }

  function regionFromBinding(binding) {
    var canvas = binding.host.closest(".slide-canvas");
    var scale = canvasScale(canvas);
    var rect = binding.host.getBoundingClientRect();
    var component = effectiveComponent(state.slides[binding.slideId], binding.componentId);
    return component.region ? Object.assign({}, component.region) : {
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
    var canvas = binding.host.closest(".slide-canvas");
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
    var canvasRect = canvas.getBoundingClientRect();
    var rect = binding.host.getBoundingClientRect();
    textRegionFrame.style.left = (rect.left - canvasRect.left) + "px";
    textRegionFrame.style.top = (rect.top - canvasRect.top) + "px";
    textRegionFrame.style.width = rect.width + "px";
    textRegionFrame.style.height = rect.height + "px";
  }

  function startTextRegionGesture(kind, event) {
    var binding = currentTextRegionBinding();
    if (!binding) return;
    event.preventDefault();
    event.stopPropagation();
    var canvas = binding.host.closest(".slide-canvas");
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

  function moveTextRegionGesture(event) {
    if (!regionGesture) return;
    event.preventDefault();
    var gesture = regionGesture;
    var scale = canvasScale(gesture.canvas);
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
    galleryImage: galleryImage,
    effectiveComponent: effectiveComponent,
    effectiveTable: effectiveTable,
    startTableColumnResize: startTableColumnResize,
    fitTextInRegion: registerTextFit,
    fitGroupInRegion: registerGroupFit,
    isEditMode: function () { return editMode; },
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
    updateVisualObject: updateVisualObject
  });

  function renderStage() {
    var index = currentIndex();
    currentId = state.order[index];
    var slide = currentSlide();
    clearFitObservers();
    removeTextRegionFrame();
    textRegionBindings.clear();
    stage.textContent = "";
    var canvas = slideShell(slide);
    renderRecipe[slide.recipe](canvas, slide);
    addFooter(canvas, slide);
    stage.appendChild(canvas);
    stage.classList.toggle("edit-mode", editMode);
    applyAllTextRegions();
    if (window.ResizeObserver) {
      var canvasObserver = new ResizeObserver(function () {
        requestAnimationFrame(function () {
          if (!canvas.isConnected) return;
          applyAllTextRegions();
          syncTextRegionFrame();
        });
      });
      canvasObserver.observe(canvas);
      fitObservers.push(canvasObserver);
    }
    position.textContent = (index + 1) + " / " + state.order.length;
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
    if (!selected || selected.visualObject || !state.slides[selected.slideId]) return null;
    return effectiveComponent(state.slides[selected.slideId], selected.componentId);
  }

  function renderTools() {
    var component = selectedComponent();
    var textSelected = editMode && component && component.kind === "text";
    var imageSelected = editMode && component && component.kind === "image";
    document.querySelectorAll("[data-font-delta], [data-color]").forEach(function (button) { button.disabled = !textSelected; });
    document.querySelectorAll("[data-image-delta]").forEach(function (button) { button.disabled = !imageSelected; });
    var objectSelected = Boolean(editMode && selected && selected.visualObject);
    document.querySelector("[data-reset-component]").disabled = !(editMode && (component || objectSelected));
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
    renderStage();
    renderThumbs();
    renderTools();
    undoButton.disabled = !undoBase;
    editToggle.textContent = editMode ? "Done editing" : "Enable edit";
    editToggle.classList.toggle("active", editMode);
  }

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
  document.querySelectorAll("[data-table-action]").forEach(function (button) {
    button.addEventListener("click", function () {
      mutateSelectedTable(button.getAttribute("data-table-action"));
    });
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

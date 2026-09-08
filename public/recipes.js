/* Canonical scientific compositions. The editor injects semantic leaf helpers. */
(function (global) {
  "use strict";

  // Documentation lives beside the layout implementation, never per slide.
  global.scientificRecipeGuides = {
    "slide-index": {use:"Navigate a deck without duplicating its mutable order or visibility.",owns:"Section labels, semantic route links, current-order sorting, and revision-safe per-slide/section visibility controls."},
    "evidence-figure": {use:"Show a retained scientific figure without changing its pixels.",owns:"A contained, uncropped image region, up to four aligned labels, and a bounded caption."},
    "hero-equation": {use:"Introduce one organizing relation.",owns:"A dominant fitted LaTeX region, aligned local definitions, and an optional question region."},
    "section-divider": {use:"Mark a change of question or method.",owns:"One bounded, vertically centered headline region; optional eyebrow and protocol."},
    "chart-panels": {use: "Compare source-native scientific plots, singly or in aligned panels.", owns: "Bounded plot regions, shared axis regions, native log axes, hover, zoom, export, and semantic annotation editing."},
    "hero-plot": {use: "Compare measured trajectories on one pair of axes.", owns: "Plot region, axes, legend, series styling, and protocol placement."},
    "evidence-table": {use: "Compare aligned values and emphasize selected cells.", owns: "Column alignment, padded cells, bounded whole-table fitting, and native table editing."},
    "mechanism-pipeline": {use: "Explain a process through connected states or models.", owns: "Node sizing, ranked layout, connector routing, and fitted text regions."},
    "vector-geometry": {use: "Explain vectors, projections, angles, and equal-norm constructions.", owns: "Equal-aspect coordinates, proportional scaling, vector handles, and bounded math labels. Authors supply meaningful geometry."},
    "hierarchical-gallery": {use: "Explore images by facets and identity pages.", owns: "Image regions, compact controls, fitted captions, metric placement, and persistent selection."},
    "target-accessibility": {use: "Compare qualitative target decompositions and model reach.", owns: "Aligned signal regions, reach marks, shared legend, and bounded labels."}
  };

  global.createScientificSlideRecipes = function (api) {
    var svgElement = api.svgElement;
    var editableText = api.editableText;
    var bindTextRegion = api.bindTextRegion;
    var galleryImage = api.galleryImage;
    var effectiveComponent = api.effectiveComponent;
    var effectiveTable = api.effectiveTable;
    var startTableColumnResize = api.startTableColumnResize;
    var fitTextInRegion = api.fitTextInRegion;
    var fitGroupInRegion = api.fitGroupInRegion;
    var objectsForSlide = api.objectsForSlide;
    var selectedObjectId = api.selectedObjectId;
    var selectVisualObject = api.selectVisualObject;
    var updateVisualObject = api.updateVisualObject;

    global.renderScientificFacetControls = function (host, slide, selectors, selection, onChange) {
      host.textContent = "";
      selectors.forEach(function (selector) {
        var group = document.createElement("div"); group.className = "gallery-selector";
        group.appendChild(editableText(slide, selector.label, "span", "gallery-selector-label"));
        var options = document.createElement("div"); options.className = "gallery-option-row";
        selector.options.forEach(function (option) {
          var button = document.createElement("button"); button.type = "button";
          button.textContent = effectiveComponent(slide, option.label).text;
          button.setAttribute("aria-pressed", String(selection[selector.id] === option.value));
          button.addEventListener("click", function (event) { event.stopPropagation(); onChange(selector.id, option.value); });
          options.appendChild(button);
        });
        group.appendChild(options); host.appendChild(group);
      });
    };

    function heroPlot(canvas, slide) {
      var data = slide.data;
      var body = document.createElement("div");
      body.className = "recipe-body hero-plot-body";
      var legend = document.createElement("div");
      legend.className = "plot-legend";
      data.series.forEach(function (series) {
        var item = document.createElement("div");
        item.className = "legend-item";
        var swatch = document.createElement("span");
        swatch.className = "legend-swatch" + (series.dash ? " dashed" : "");
        swatch.style.setProperty("--series", series.color);
        item.appendChild(swatch);
        item.appendChild(editableText(slide, series.label, "span", "legend-label"));
        legend.appendChild(item);
      });
      body.appendChild(legend);

      var chart = document.createElement("div");
      chart.className = "chart-layout";
      chart.appendChild(editableText(slide, data.yAxis.label, "div", "axis-label y-axis-label"));
      var frame = document.createElement("div");
      frame.className = "chart-frame";
      var svg = svgElement("svg", {viewBox: "0 0 1000 480", role: "img", "aria-label": "Synthetic multi-series learning curves"});
      var left = 72, right = 955, top = 24, bottom = 420;
      var x0 = data.xAxis.domain[0], x1 = data.xAxis.domain[1];
      var y0 = data.yAxis.domain[0], y1 = data.yAxis.domain[1];
      function x(value) { return left + (value - x0) / (x1 - x0) * (right - left); }
      function y(value) { return bottom - (value - y0) / (y1 - y0) * (bottom - top); }
      data.yAxis.ticks.forEach(function (tick) {
        svg.appendChild(svgElement("line", {x1: left, y1: y(tick), x2: right, y2: y(tick), class: "chart-grid"}));
        var label = svgElement("text", {x: left - 18, y: y(tick) + 6, class: "chart-tick", "text-anchor": "end"});
        label.textContent = tick;
        svg.appendChild(label);
      });
      data.xAxis.ticks.forEach(function (tick) {
        var label = svgElement("text", {x: x(tick), y: bottom + 38, class: "chart-tick", "text-anchor": "middle"});
        label.textContent = tick;
        svg.appendChild(label);
      });
      svg.appendChild(svgElement("line", {x1: left, y1: bottom, x2: right, y2: bottom, class: "chart-axis"}));
      svg.appendChild(svgElement("line", {x1: left, y1: top, x2: left, y2: bottom, class: "chart-axis"}));
      data.series.forEach(function (series) {
        var points = series.points.map(function (point) { return x(point[0]) + "," + y(point[1]); }).join(" ");
        svg.appendChild(svgElement("polyline", {
          points: points, fill: "none", stroke: series.color, "stroke-width": "7",
          "stroke-linejoin": "round", "stroke-linecap": "round",
          "stroke-dasharray": series.dash ? "14 12" : "none"
        }));
        series.points.forEach(function (point) {
          svg.appendChild(svgElement("circle", {cx: x(point[0]), cy: y(point[1]), r: "6.5", fill: "white", stroke: series.color, "stroke-width": "4"}));
        });
      });
      frame.appendChild(svg);
      frame.appendChild(editableText(slide, data.xAxis.label, "div", "axis-label x-axis-label"));
      chart.appendChild(frame);
      body.appendChild(chart);
      canvas.appendChild(body);
    }

    function slideIndex(canvas,slide) {
      var body=document.createElement('div');body.className='recipe-body slide-index-body';
      function visibilityButton(ids) {
        var hidden=ids.every(api.isSlideHidden),button=document.createElement('button');
        button.type='button';button.className='index-visibility';button.textContent=hidden?'Show':'Hide';
        button.setAttribute('aria-label',(hidden?'Show ':'Hide ')+ids.join(', '));
        button.disabled=!api.isEditMode();
        button.addEventListener('click',function(event) {event.preventDefault();event.stopPropagation();api.setSlidesHidden(ids,!hidden);});
        return button;
      }
      slide.data.sections.forEach(function(section) {
        var group=document.createElement('section'),head=document.createElement('header');
        head.appendChild(editableText(slide,section.heading,'div','index-section-heading'));
        head.appendChild(visibilityButton(section.items.map(function(item) {return item.slide;})));
        group.appendChild(head);
        var links=document.createElement('div');links.className='index-links';
        section.items.slice().sort(function(a,b) {return api.orderOfSlide(a.slide)-api.orderOfSlide(b.slide);}).forEach(function(item) {
          var row=document.createElement('div');row.className='index-link-row';
          if(api.isSlideHidden(item.slide)) row.classList.add('index-destination-hidden');
          var link=document.createElement('a');link.href='#'+item.slide;
          link.appendChild(editableText(slide,item.label,'div','index-link-label'));
          link.addEventListener('click',function(event) {if(api.isEditMode())event.preventDefault();});
          row.appendChild(link);row.appendChild(visibilityButton([item.slide]));links.appendChild(row);
        });
        group.appendChild(links);body.appendChild(group);
      });
      canvas.appendChild(body);
    }

    function evidenceTable(canvas, slide) {
      if(slide.data.tables) {
        var collection=document.createElement('div');
        collection.className='recipe-body table-panels-body';
        var selector=slide.data.tableSelector;
        if(selector) collection.classList.add('selectable-tables');
        var storageKey='online-slide.table-view.'+slide.id;
        var active=slide.data.initialTable || slide.data.tables[0].id;
        if(selector) {
          try { active=localStorage.getItem(storageKey) || active; } catch (_) {}
          if(!slide.data.tables.some(function(table){return table.id===active;})) active=slide.data.tables[0].id;
        }
        function renderTables() {
          collection.textContent='';
          if(selector) {
            var controls=document.createElement('div');
            global.renderScientificFacetControls(controls,slide,[Object.assign({id:'table'},selector)],{table:active},function(_,value){
              active=value;
              try {localStorage.setItem(storageKey,value);} catch (_) {}
              renderTables();
            });
            collection.appendChild(controls);
          }
          slide.data.tables.filter(function(table){return !selector || table.id===active;}).forEach(function(data) {
          if(data.heading) collection.appendChild(editableText(slide,data.heading,'div','table-panel-heading'));
          if(data.visibility) collection.appendChild(editableText(slide,data.visibility,'div','table-panel-control'));
          evidenceTable(collection,Object.assign({},slide,{data:data,_tableKey:slide.id+'::table::'+data.id}));
          });
        }
        canvas.appendChild(collection);
        renderTables();
        return;
      }
      var model = effectiveTable(slide);
      var body = document.createElement("div");
      body.className = "recipe-body table-body";
      if(slide.data.visibility && effectiveComponent(slide,slide.data.visibility).hidden) body.classList.add('curator-hidden-component');
      body.setAttribute('data-table-panel-id',slide.data.id || 'main');
      var table = document.createElement("table");
      table.className = "evidence-table";
      table.setAttribute("data-native-table", slide._tableKey || slide.id);
      var colgroup = document.createElement("colgroup");
      var totalWidth = model.columns.reduce(function (sum, column) { return sum + column.width; }, 0);
      model.columns.forEach(function (column) {
        var col = document.createElement("col");
        col.setAttribute("data-table-column-id", column.id);
        col.style.width = (column.width / totalWidth * 100).toFixed(3) + "%";
        colgroup.appendChild(col);
      });
      table.appendChild(colgroup);
      var head = document.createElement("thead");
      var headRow = document.createElement("tr");
      model.columns.forEach(function (column, columnIndex) {
        var th = document.createElement("th");
        th.setAttribute("data-table-cell", "header:" + column.id);
        th.setAttribute("data-table-row-id", "table-header");
        th.setAttribute("data-table-row-index", "-1");
        th.setAttribute("data-table-column-id", column.id);
        th.setAttribute("data-table-column-index", String(columnIndex));
        th.appendChild(editableText(slide, column.label, "div", "table-heading"));
        var resizer = document.createElement("button");
        resizer.type = "button";
        resizer.className = "table-column-resizer";
        resizer.setAttribute("aria-label", "Resize " + effectiveComponent(slide, column.label).text + " column");
        resizer.addEventListener("pointerdown", function (event) {
          startTableColumnResize(slide, column.id, event);
        });
        th.appendChild(resizer);
        headRow.appendChild(th);
      });
      head.appendChild(headRow);
      table.appendChild(head);
      var tbody = document.createElement("tbody");
      model.rows.forEach(function (row, rowIndex) {
        var tr = document.createElement("tr");
        tr.setAttribute("data-table-row", row.id);
        var label = document.createElement("th");
        label.scope = "row";
        label.setAttribute("data-table-cell", row.id + ":" + model.columns[0].id);
        label.setAttribute("data-table-row-id", row.id);
        label.setAttribute("data-table-row-index", String(rowIndex));
        label.setAttribute("data-table-column-id", model.columns[0].id);
        label.setAttribute("data-table-column-index", "0");
        label.appendChild(editableText(slide, row.label, "div", "table-row-label"));
        tr.appendChild(label);
        row.cells.forEach(function (componentId, index) {
          var td = document.createElement("td");
          var column = model.columns[index + 1];
          td.setAttribute("data-table-cell", row.id + ":" + column.id);
          td.setAttribute("data-table-row-id", row.id);
          td.setAttribute("data-table-row-index", String(rowIndex));
          td.setAttribute("data-table-column-id", column.id);
          td.setAttribute("data-table-column-index", String(index + 1));
          if (componentId === row.best) td.classList.add("row-best");
          if (componentId === row.globalBest) td.classList.add("global-best");
          td.appendChild(editableText(slide, componentId, "div", "table-value"));
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      body.appendChild(table);
      canvas.appendChild(body);
      fitGroupInRegion(table, body, {
        mode: "evidence-table-region",
        property: "--table-fit-scale",
        minScale: 0.58,
        maxScale: 1,
        contentSelector: ".table-heading, .table-row-label, .table-value"
      });
    }

    function targetAccessibility(canvas, slide) {
      var body = document.createElement("div");
      body.className = "recipe-body accessibility-body";
      var panels = document.createElement("div");
      panels.className = "accessibility-panels";
      var records = [];
      slide.data.panels.forEach(function (panel) {
        var total = panel.shares.reduce(function (sum, value) { return sum + value; }, 0);
        var common = panel.shares[0] / total * 100;
        var recurrent = (panel.shares[0] + panel.shares[1]) / total * 100;
        var article = document.createElement("article");
        article.className = "accessibility-panel";
        article.setAttribute("data-accessibility-panel", panel.id);
        article.addEventListener("click", function (event) {
          if (api.isEditMode()) event.stopPropagation();
        });
        article.style.setProperty("--common-share", common.toFixed(3) + "%");
        article.style.setProperty("--recurrent-share", recurrent.toFixed(3) + "%");
        var header = document.createElement("header");
        header.className = "accessibility-panel-header";
        header.appendChild(editableText(slide, panel.title, "h2", "accessibility-panel-title"));
        header.appendChild(editableText(slide, panel.summary, "p", "accessibility-panel-summary"));
        article.appendChild(header);
        var target = document.createElement("div");
        target.className = "accessibility-target-row";
        target.appendChild(editableText(slide, panel.target, "div", "accessibility-target-label"));
        var barSlot = document.createElement("div");
        barSlot.className = "accessibility-target-slot";
        var bar = document.createElement("div");
        bar.className = "accessibility-signal";
        ["common", "depth", "inaccessible"].forEach(function (kind, index) {
          var segment = document.createElement("span");
          segment.className = "accessibility-segment segment-" + kind;
          segment.style.flexGrow = String(panel.shares[index]);
          bar.appendChild(segment);
        });
        barSlot.appendChild(bar);
        target.appendChild(barSlot);
        article.appendChild(target);
        var reaches = document.createElement("div");
        reaches.className = "accessibility-reaches";
        var b4 = document.createElement("div");
        b4.className = "accessibility-reach-row reach-b4";
        b4.appendChild(editableText(slide, panel.b4Fit, "span", "accessibility-reach-label"));
        var b4Slot = document.createElement("span");
        b4Slot.className = "accessibility-reach-slot";
        var b4Line = document.createElement("span");
        b4Line.className = "accessibility-reach-line";
        b4Slot.appendChild(b4Line);
        b4.appendChild(b4Slot);
        reaches.appendChild(b4);
        var r3 = document.createElement("div");
        r3.className = "accessibility-reach-row reach-r3";
        r3.appendChild(editableText(slide, panel.r3Fit, "span", "accessibility-reach-label"));
        var r3Slot = document.createElement("span");
        r3Slot.className = "accessibility-reach-slot";
        var r3Line = document.createElement("span");
        r3Line.className = "accessibility-reach-line";
        r3Slot.appendChild(r3Line);
        r3.appendChild(r3Slot);
        reaches.appendChild(r3);
        article.appendChild(reaches);
        panels.appendChild(article);
        records.push({id: panel.id + "-target", kind: "accessibility-target",
          mode: "rect", article: article, element: bar});
        records.push({id: panel.id + "-b4-reach", kind: "accessibility-reach",
          mode: "line", article: article, element: b4Line});
        records.push({id: panel.id + "-r3-reach", kind: "accessibility-reach",
          mode: "line", article: article, element: r3Line});
      });
      body.appendChild(panels);
      var key = document.createElement("div");
      key.className = "accessibility-key";
      ["common", "depth", "inaccessible"].forEach(function (kind, index) {
        var item = document.createElement("div");
        item.className = "accessibility-key-item";
        var swatch = document.createElement("span");
        swatch.className = "accessibility-key-swatch segment-" + kind;
        item.appendChild(swatch);
        item.appendChild(editableText(slide, slide.data.legend[index], "span", "accessibility-key-label"));
        key.appendChild(item);
      });
      body.appendChild(key);
      body.appendChild(editableText(slide, slide.data.equation, "div", "accessibility-equation"));
      canvas.appendChild(body);

      wireVisualObjects(slide,records);
    }

    // One bounded drag/resize implementation for authored shapes and recipe
    // marks. Coordinates belong to the owning plane, never the viewport.
    function wireVisualObjects(slide,records) {
      var objectState=api.objectsForSlide(slide);
      function rounded(value) { return Math.round(value * 10000) / 10000; }

      function rectGeometry(record) {
        var outer = record.article.getBoundingClientRect();
        var box = record.element.getBoundingClientRect();
        return {kind: record.kind,
          x: rounded((box.left - outer.left) / outer.width),
          y: rounded((box.top - outer.top) / outer.height),
          width: rounded(box.width / outer.width),
          height: rounded(box.height / outer.height)};
      }

      function lineGeometry(record) {
        var outer = record.article.getBoundingClientRect();
        var box = record.element.getBoundingClientRect();
        return {kind: record.kind,
          from: [rounded((box.left - outer.left) / outer.width),
            rounded((box.top + box.height / 2 - outer.top) / outer.height)],
          to: [rounded((box.right - outer.left) / outer.width),
            rounded((box.top + box.height / 2 - outer.top) / outer.height)]};
      }

      function sourceGeometry(record) {
        if(record.source) return record.source;
        return record.mode === "rect" ? rectGeometry(record) : lineGeometry(record);
      }

      function applyGeometry(record, geometry) {
        var element = record.element;
        element.classList.add("accessibility-object-detached");
        if (record.mode === "rect") {
          element.style.left = (geometry.x * 100) + "%";
          element.style.top = (geometry.y * 100) + "%";
          element.style.width = (geometry.width * 100) + "%";
          element.style.height = (geometry.height * 100) + "%";
          element.style.transform = "none";
        } else {
          var width = record.article.clientWidth;
          var height = record.article.clientHeight;
          var dx = (geometry.to[0] - geometry.from[0]) * width;
          var dy = (geometry.to[1] - geometry.from[1]) * height;
          element.style.left = (geometry.from[0] * 100) + "%";
          element.style.top = (geometry.from[1] * 100) + "%";
          element.style.width = Math.max(2, Math.hypot(dx, dy)) + "px";
          element.style.transform = "translateY(-50%) rotate(" + Math.atan2(dy, dx) + "rad)";
        }
        positionControls(record, geometry);
      }

      function positionControls(record, geometry) {
        if (!record.controls) return;
        if(record.selector) {
          record.selector.style.left=(geometry.x*100)+'%';record.selector.style.top=(geometry.y*100)+'%';
        }
        if (record.mode === "rect") {
          record.controls.style.left = (geometry.x * 100) + "%";
          record.controls.style.top = (geometry.y * 100) + "%";
          record.controls.style.width = (geometry.width * 100) + "%";
          record.controls.style.height = (geometry.height * 100) + "%";
        } else {
          var points = [geometry.from, geometry.to,
            [(geometry.from[0] + geometry.to[0]) / 2, (geometry.from[1] + geometry.to[1]) / 2]];
          [record.startHandle, record.endHandle, record.moveHandle].forEach(function (handle, index) {
            handle.style.left = (points[index][0] * 100) + "%";
            handle.style.top = (points[index][1] * 100) + "%";
          });
        }
      }

      function showSelected(record) {
        records.forEach(function (item) {
          item.element.classList.toggle("selected-visual-object", item === record);
          if (item.controls) item.controls.hidden = item !== record;
        });
        api.selectVisualObject(slide.id, record.id, record.kind);
      }

      function boundedPoint(point) {
        return [Math.max(0, Math.min(1, rounded(point[0]))),
          Math.max(0, Math.min(1, rounded(point[1])))];
      }

      function startGesture(record, gesture, event) {
        if (!api.isEditMode()) return;
        if(record.kind==='recipe-frame' && gesture==='move' && event.target!==record.element) return;
        event.preventDefault();
        event.stopPropagation();
        // Selection may reveal a midpoint handle beneath the pointer. Keep
        // the gesture's up/click on its original owner instead of the canvas.
        if(event.currentTarget.setPointerCapture) event.currentTarget.setPointerCapture(event.pointerId);
        showSelected(record);
        var initial = objectState[record.id] || sourceGeometry(record);
        var startX = event.clientX;
        var startY = event.clientY;
        var moved = false;
        function onMove(moveEvent) {
          moveEvent.preventDefault();
          var rendered = record.article.getBoundingClientRect();
          var dx = (moveEvent.clientX - startX) / rendered.width;
          var dy = (moveEvent.clientY - startY) / rendered.height;
          if (Math.abs(dx) + Math.abs(dy) < .001 && !moved) return;
          moved = true;
          var next;
          if (record.mode === "rect") {
            next = Object.assign({}, initial);
            if (gesture === "resize") {
              next.width = Math.max(.03, Math.min(1 - initial.x, rounded(initial.width + dx)));
              next.height = Math.max(.012, Math.min(1 - initial.y, rounded(initial.height + dy)));
            } else {
              next.x = Math.max(0, Math.min(1 - initial.width, rounded(initial.x + dx)));
              next.y = Math.max(0, Math.min(1 - initial.height, rounded(initial.y + dy)));
            }
          } else {
            next = {kind: record.kind, from: initial.from.slice(), to: initial.to.slice()};
            if (gesture === "start") next.from = boundedPoint([initial.from[0] + dx, initial.from[1] + dy]);
            else if (gesture === "end") next.to = boundedPoint([initial.to[0] + dx, initial.to[1] + dy]);
            else {
              var minX = Math.min(initial.from[0], initial.to[0]);
              var maxX = Math.max(initial.from[0], initial.to[0]);
              var minY = Math.min(initial.from[1], initial.to[1]);
              var maxY = Math.max(initial.from[1], initial.to[1]);
              dx = Math.max(-minX, Math.min(1 - maxX, dx));
              dy = Math.max(-minY, Math.min(1 - maxY, dy));
              next.from = boundedPoint([initial.from[0] + dx, initial.from[1] + dy]);
              next.to = boundedPoint([initial.to[0] + dx, initial.to[1] + dy]);
            }
          }
          objectState[record.id] = next;
          applyGeometry(record, next);
          api.updateVisualObject(slide.id, record.id, record.kind, next, false);
        }
        function onEnd() {
          document.removeEventListener("pointermove", onMove);
          document.removeEventListener("pointerup", onEnd);
          document.removeEventListener("pointercancel", onEnd);
          document.body.classList.remove("moving-visual-object");
          if (moved) api.updateVisualObject(slide.id, record.id, record.kind,
            objectState[record.id], true);
        }
        document.body.classList.add("moving-visual-object");
        document.addEventListener("pointermove", onMove);
        document.addEventListener("pointerup", onEnd);
        document.addEventListener("pointercancel", onEnd);
      }

      records.forEach(function (record) {
        record.element.classList.add("editable-visual-object");
        record.element.setAttribute("data-visual-object-id", record.id);
        record.element.setAttribute("data-visual-object-kind", record.kind);
        record.element.setAttribute("aria-label", record.id + " editable " + record.mode);
        record.element.addEventListener("pointerdown", function (event) {
          startGesture(record, "move", event);
        });
        record.element.addEventListener("click", function (event) {
          if (api.isEditMode()) event.stopPropagation();
        });
        if (record.mode === "rect") {
          var frame = document.createElement("div");
          frame.className = "accessibility-object-frame";
          frame.hidden = true;
          var resize = document.createElement("button");
          resize.type = "button";
          resize.className = "accessibility-object-resize";
          resize.setAttribute("aria-label", "Resize " + record.id);
          resize.addEventListener("pointerdown", function (event) {
            startGesture(record, "resize", event);
          });
          frame.appendChild(resize);
          record.controls = frame;
          frame.addEventListener("click", function (event) { event.stopPropagation(); });
          record.article.appendChild(frame);
          if(record.kind==='recipe-frame') {
            var selector=document.createElement('button');selector.type='button';selector.className='recipe-frame-select';
            selector.textContent='Layout';selector.setAttribute('aria-label','Move layout frame');
            selector.addEventListener('pointerdown',function(event){startGesture(record,'frame',event);});
            selector.addEventListener('click',function(event){event.stopPropagation();});
            record.selector=selector;record.article.appendChild(selector);
          }
        } else {
          var controls = document.createElement("div");
          controls.className = "accessibility-line-controls";
          controls.hidden = true;
          [["start", "accessibility-line-endpoint"], ["end", "accessibility-line-endpoint"],
           ["move", "accessibility-line-move"]].forEach(function (entry) {
            var handle = document.createElement("button");
            handle.type = "button";
            handle.className = entry[1];
            handle.setAttribute("aria-label", entry[0] + " handle for " + record.id);
            handle.addEventListener("pointerdown", function (event) {
              startGesture(record, entry[0], event);
            });
            controls.appendChild(handle);
            if (entry[0] === "start") record.startHandle = handle;
            else if (entry[0] === "end") record.endHandle = handle;
            else record.moveHandle = handle;
          });
          record.controls = controls;
          controls.addEventListener("click", function (event) { event.stopPropagation(); });
          record.article.appendChild(controls);
        }
      });

      requestAnimationFrame(function () {
        records.forEach(function (record) {
          if (objectState[record.id] || record.source) applyGeometry(record, objectState[record.id] || record.source);
          else positionControls(record, sourceGeometry(record));
          if (api.selectedObjectId(slide) === record.id) showSelected(record);
        });
      });
      if (window.ResizeObserver) {
        records.forEach(function (record) {
          var observer = new ResizeObserver(function () {
            if (!record.article.isConnected) { observer.disconnect(); return; }
            var geometry = objectState[record.id] || sourceGeometry(record);
            if (objectState[record.id]) applyGeometry(record, geometry);
            else positionControls(record, geometry);
          });
          observer.observe(record.article);
        });
      }
    }

    function annotations(canvas,slide) {
      var records=[];
      if(slide.frame) {
        var body=canvas.querySelector(':scope > .recipe-body');
        if(body) records.push({id:slide.frame.id,kind:'recipe-frame',mode:'rect',article:canvas,element:body,
          source:Object.assign({kind:'recipe-frame'},slide.frame.geometry)});
      }
      (slide.annotations || []).forEach(function(item) {
        if(item.kind==='text') {
          var text=editableText(slide,item.component,'div','slide-annotation-text');
          canvas.appendChild(text);
          bindTextRegion(slide,item.component,text,text,{alwaysFit:true});
          return;
        }
        var element=document.createElement('div');
        element.className='slide-annotation-shape annotation-'+item.kind;
        element.style.setProperty('--annotation-color',item.color);
        element.style.setProperty('--annotation-width',(item.strokeWidth || 3)+'px');
        element.style.borderRadius=(item.cornerRadius || 0)+'px';
        canvas.appendChild(element);
        records.push({id:item.id,kind:item.kind==='rect'?'annotation-rect':'annotation-line',
          mode:item.kind==='rect'?'rect':'line',article:canvas,element:element,
          source:Object.assign({kind:item.kind==='rect'?'annotation-rect':'annotation-line'},item.geometry)});
      });
      wireVisualObjects(slide,records);
    }

    function mechanismPipeline(canvas, slide) {
      var body = document.createElement("div");
      body.className = "recipe-body diagram-body";
      var plane = document.createElement("div");
      plane.className = "diagram-plane";
      var paperHost = document.createElement("div");
      paperHost.className = "joint-paper";
      if (api.isEditMode()) paperHost.addEventListener("click", function (event) { event.stopPropagation(); });
      plane.appendChild(paperHost);
      var nodeLabels = {};
      var edgeLabels = {};
      slide.data.nodes.forEach(function (node) {
        var block = document.createElement("div");
        block.className = "diagram-node-copy tone-" + (node.tone || "quiet");
        block.setAttribute("data-diagram-node-id", node.id);
        var content = document.createElement("div");
        content.className = "diagram-node-content";
        content.appendChild(editableText(slide, node.label, "div", "node-label"));
        if (node.detail) content.appendChild(editableText(slide, node.detail, "div", "node-detail"));
        block.appendChild(content);
        nodeLabels[node.id] = block;
        plane.appendChild(block);
        fitGroupInRegion(content, block, {
          mode: "diagram-node-region",
          property: "--diagram-node-fit-scale",
          minScale: .35,
          maxScale: 1,
          contentSelector: ".node-label, .node-detail",
          tolerance: 2
        });
      });
      slide.data.edges.forEach(function (edge) {
        if (!edge.label) return;
        var label = editableText(slide, edge.label, "div", "edge-label");
        label.setAttribute("data-diagram-edge-id", edge.id);
        edgeLabels[edge.id] = label;
        plane.appendChild(label);
      });
      body.appendChild(plane);
      canvas.appendChild(body);
      if (!window.ScientificDiagramRuntime) throw new Error("JointJS diagram runtime is missing");

      function measureNodes() {
        var sizes = {};
        // Measure in the slide's own coordinate system. The editor presents
        // the 1920x1080 canvas through a CSS transform; getBoundingClientRect()
        // includes that outer transform and used to make every node look
        // artificially small to the layout engine. offset*/scroll* dimensions
        // intentionally ignore ancestor transforms, so the same authored
        // diagram receives the same natural node sizes in editor and
        // presentation modes.
        var planeWidth = plane.clientWidth || 1200;
        slide.data.nodes.forEach(function (node) {
          var block = nodeLabels[node.id];
          if (node.sizing === "fixed") {
            sizes[node.id] = {width: node.width, height: node.height};
            return;
          }
          var minWidth = Math.max(154, Math.min(220, planeWidth * .13));
          var detail = node.detail && slide.components[node.detail];
          var mathDetail = detail && detail.render === "latex";
          // A readable word is the minimum semantic unit. Give ordinary
          // prose enough width to wrap at spaces before the group fitter
          // scales the complete composition; do not force mid-word breaks
          // merely because the editor stage is narrower than fullscreen.
          var maxWidth = Math.max(minWidth, Math.min(mathDetail ? 400 : 360, planeWidth * .32));
          block.style.setProperty("--diagram-node-min-width", minWidth + "px");
          block.style.setProperty("--diagram-node-max-width", maxWidth + "px");
          block.classList.add("diagram-node-measuring");
          var measuredWidth = Math.max(block.offsetWidth, block.scrollWidth);
          var measuredHeight = Math.max(block.offsetHeight, block.scrollHeight);
          sizes[node.id] = {
            // Text and KaTeX can differ by a fractional pixel between the
            // hidden measurement pass and final scaled paint. Keep a tiny
            // intrinsic safety allowance so a correctly sized node never
            // exposes a scrollbar or clips the last glyph.
            width: Math.ceil(Math.max(minWidth, Math.min(maxWidth, measuredWidth + 6))),
            // Chromium line boxes can gain 1–3 px when painted at a
            // fractional scale. Reserve a full optical gutter as well:
            // containment alone can still leave a dense last baseline
            // visually pressed against the node border.
            height: Math.ceil(Math.max(112, measuredHeight + 40))
          };
          block.classList.remove("diagram-node-measuring");
        });
        return sizes;
      }

      requestAnimationFrame(function () {
        var initialSizes = measureNodes();
        var runtimeData = Object.assign({}, slide.data, {
          nodes: slide.data.nodes.map(function (node) {
            var size = initialSizes[node.id];
            return Object.assign({}, node, {layoutWidth: size.width, layoutHeight: size.height});
          })
        });
        var diagram = window.ScientificDiagramRuntime.renderPipeline(paperHost, runtimeData, {
          interactive: api.isEditMode(),
          objects: objectsForSlide(slide),
          selectedId: selectedObjectId(slide),
          onSelect: function (kind, id) {
            selectVisualObject(slide.id, id, kind);
          },
          onObjectChange: function (kind, id, geometry, commit) {
            updateVisualObject(slide.id, id, kind, geometry, commit);
          },
          onNodePosition: function (id, box, size) {
            var node = nodeLabels[id];
            if (!node) return;
            node.style.left = (box.x / size.width * 100) + "%";
            node.style.top = (box.y / size.height * 100) + "%";
            node.style.width = (box.width / size.width * 100) + "%";
            node.style.height = (box.height / size.height * 100) + "%";
            node.style.transform = "none";
          },
          onEdgePosition: function (id, point, size) {
            var label = edgeLabels[id];
            if (!label) return;
            label.style.left = (point.x / size.width * 100) + "%";
            label.style.top = (point.y / size.height * 100) + "%";
          }
        });
        paperHost.dataset.diagramMeasurement = "untransformed-slide-coordinates";
        var reflowTimer = null;
        function scheduleReflow() {
          clearTimeout(reflowTimer);
          reflowTimer = setTimeout(function () {
            if (!plane.isConnected) return;
            diagram.resizeNodes(measureNodes());
          }, 40);
        }
        plane.addEventListener("input", scheduleReflow);
        // One immediate settled pass absorbs final wrapping and KaTeX metrics
        // before the diagram becomes interactive; no timer may later undo a
        // curator drag.
        requestAnimationFrame(function () {
          if (plane.isConnected) diagram.resizeNodes(measureNodes());
        });
        if (window.ResizeObserver) {
          var observer = new ResizeObserver(function () {
            if (!plane.isConnected) {
              observer.disconnect();
              return;
            }
            scheduleReflow();
          });
          observer.observe(plane);
        }
      });
    }

    function vectorGeometry(canvas, slide) {
      var body = document.createElement("div");
      body.className = "recipe-body vector-geometry-body";
      var plane = document.createElement("div");
      plane.className = "vector-geometry-plane";
      var board = document.createElement("div");
      board.className = "jsxgraph-host";
      board.id = "jsxgraph-" + slide.id;
      plane.appendChild(board);
      var worldLabels=[];
      (slide.data.labels || []).forEach(function (label) {
        var region = document.createElement("div");
        region.className = "vector-label-region";
        region.style.left = label.box.x + "%";
        region.style.top = label.box.y + "%";
        region.style.width = label.box.width + "%";
        region.style.height = label.box.height + "%";
        if(label.space==='world')worldLabels.push({label:label,region:region});
        region.style.justifyContent = label.box.align || "center";
        region.style.alignItems = label.box.valign || "center";
        var node = editableText(slide, label.component, "div", "vector-label" + (label.tone ? " tone-" + label.tone : ""));
        region.appendChild(node);
        plane.appendChild(region);
        bindTextRegion(slide, label.component, node, region, {
          alwaysFit: true,
          fitMode: "vector-label-region",
          minSize: 10
        });
      });
      body.appendChild(plane);
      var equations = document.createElement("div");
      equations.className = "vector-equations";
      (slide.data.equations || []).forEach(function (componentId) {
        equations.appendChild(editableText(slide, componentId, "div", "vector-equation"));
      });
      body.appendChild(equations);
      canvas.appendChild(body);
      if (!window.ScientificGeometryRuntime) throw new Error("JSXGraph geometry runtime is missing");
      requestAnimationFrame(function () {
        var geometry=window.ScientificGeometryRuntime.renderVectorPlane(board, slide.data, {
          interactive: api.isEditMode(),
          objects: objectsForSlide(slide),
          selectedId: selectedObjectId(slide),
          onSelect: function (kind, id) {
            selectVisualObject(slide.id, id, kind);
          },
          onObjectChange: function (kind, id, geometry, commit) {
            updateVisualObject(slide.id, id, kind, geometry, commit);
          }
        });
        // JSXGraph owns the letterboxing transform. Authored world regions
        // use that same transform; a curator's explicit region takes priority.
        function alignWorldLabels() {
          worldLabels.forEach(function(item){
            var box=item.label.box,style=item.region.style;
            style.left=(geometry.origin.scrCoords[1]+box.x*geometry.unitX)+'px';
            style.top=(geometry.origin.scrCoords[2]-box.y*geometry.unitY)+'px';
            // Curator x/y are translations relative to this authored anchor,
            // not replacements for it. Only their explicit size overrides it.
            if(!effectiveComponent(slide,item.label.component).region) {
              style.width=(box.width*geometry.unitX)+'px';
              style.height=(box.height*geometry.unitY)+'px';
            }
          });
        }
        alignWorldLabels();
        if(worldLabels.length)geometry.on('boundingbox',alignWorldLabels);
      });
    }

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

    return {
      "evidence-figure": function(canvas,slide) {
        var body=document.createElement('div');body.className='recipe-body evidence-figure-body';
        var labels=document.createElement('div');labels.className='evidence-figure-labels';
        (slide.data.labels||[]).forEach(function(key){labels.appendChild(editableText(slide,key,'div','evidence-figure-label'));});
        body.appendChild(labels);
        var frame=galleryImage(slide,slide.data.image);frame.classList.add('evidence-figure-frame');body.appendChild(frame);
        if(slide.data.caption)body.appendChild(editableText(slide,slide.data.caption,'div','evidence-figure-caption'));
        canvas.appendChild(body);
      },
      "hero-equation": function (canvas,slide) {
        var body=document.createElement('div');body.className='recipe-body hero-equation-body';
        if(slide.data.question) {
          body.classList.add('with-question');
          body.appendChild(editableText(slide,slide.data.question,'p','hero-equation-question'));
        }
        var frame=document.createElement('div');frame.className='hero-equation-frame';
        var equation=editableText(slide,slide.data.equation,'div','hero-equation-value');
        frame.appendChild(equation);body.appendChild(frame);
        bindTextRegion(slide,slide.data.equation,equation,frame,{alwaysFit:true,fitMode:'hero-equation',minSize:40});
        var definitions=document.createElement('div');definitions.className='hero-equation-definitions';
        slide.data.definitions.forEach(function(key){definitions.appendChild(editableText(slide,key,'div','hero-equation-definition'));});
        body.appendChild(definitions);canvas.appendChild(body);
      },
      "section-divider": function () {},
      annotations: annotations,
      "chart-panels": function (canvas, slide) { return global.renderScientificChartPanels(canvas, slide, api); },
      "hero-plot": heroPlot,
      "evidence-table": evidenceTable,
      "slide-index": slideIndex,
      "target-accessibility": targetAccessibility,
      "mechanism-pipeline": mechanismPipeline,
      "vector-geometry": vectorGeometry,
      "hierarchical-gallery": hierarchicalGallery
    };
  };
}(window));

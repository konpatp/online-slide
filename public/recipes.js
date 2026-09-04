/* Canonical scientific compositions. The editor injects semantic leaf helpers. */
(function (global) {
  "use strict";

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

    function evidenceTable(canvas, slide) {
      var model = effectiveTable(slide);
      var body = document.createElement("div");
      body.className = "recipe-body table-body";
      var table = document.createElement("table");
      table.className = "evidence-table";
      table.setAttribute("data-native-table", slide.id);
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
      var objectState = api.objectsForSlide(slide);
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
        event.preventDefault();
        event.stopPropagation();
        showSelected(record);
        var initial = objectState[record.id] || sourceGeometry(record);
        var startX = event.clientX;
        var startY = event.clientY;
        var moved = false;
        function onMove(moveEvent) {
          moveEvent.preventDefault();
          var dx = (moveEvent.clientX - startX) / record.article.clientWidth;
          var dy = (moveEvent.clientY - startY) / record.article.clientHeight;
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
          if (objectState[record.id]) applyGeometry(record, objectState[record.id]);
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
            height: Math.ceil(Math.max(112, measuredHeight + 52))
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
      (slide.data.labels || []).forEach(function (label) {
        var region = document.createElement("div");
        region.className = "vector-label-region";
        region.style.left = label.box.x + "%";
        region.style.top = label.box.y + "%";
        region.style.width = label.box.width + "%";
        region.style.height = label.box.height + "%";
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
        window.ScientificGeometryRuntime.renderVectorPlane(board, slide.data, {
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
      });
    }

    function hierarchicalGallery(canvas, slide) {
      var body = document.createElement("div");
      body.className = "recipe-body hierarchical-gallery-body";
      var controls = document.createElement("div");
      controls.className = "gallery-controls";
      var summary = document.createElement("div");
      summary.className = "gallery-summary";
      var viewHost = document.createElement("div");
      viewHost.className = "hierarchical-gallery-view";
      var storageKey = "online-slide.gallery." + slide.id;
      var defaults = {};
      slide.data.selectors.forEach(function (selector) { defaults[selector.id] = selector.options[0].value; });
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
        controls.textContent = "";
        slide.data.selectors.forEach(function (selector) {
          var group = document.createElement("div");
          group.className = "gallery-selector";
          group.appendChild(editableText(slide, selector.label, "span", "gallery-selector-label"));
          var options = document.createElement("div");
          options.className = "gallery-option-row";
          selector.options.forEach(function (option) {
            var button = document.createElement("button");
            button.type = "button";
            button.textContent = componentText(option.label);
            button.setAttribute("aria-pressed", String(galleryState.selection[selector.id] === option.value));
            button.addEventListener("click", function (event) {
              event.stopPropagation();
              galleryState.selection[selector.id] = option.value;
              galleryState.page = 0;
              saveGalleryState();
              renderGallery();
            });
            options.appendChild(button);
          });
          group.appendChild(options);
          controls.appendChild(group);
        });

        var view = activeView();
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
        grid.style.setProperty("--gallery-columns", String(slide.data.columns.length));
        grid.style.setProperty("--gallery-rows", String(page.rows.length));
        grid.appendChild(document.createElement("div"));
        slide.data.columns.forEach(function (componentId) {
          grid.appendChild(editableText(slide, componentId, "div", "gallery-heading"));
        });
        page.rows.forEach(function (row) {
          grid.appendChild(editableText(slide, row.label, "div", "gallery-row-label"));
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
      "hero-plot": heroPlot,
      "evidence-table": evidenceTable,
      "target-accessibility": targetAccessibility,
      "mechanism-pipeline": mechanismPipeline,
      "vector-geometry": vectorGeometry,
      "hierarchical-gallery": hierarchicalGallery
    };
  };
}(window));

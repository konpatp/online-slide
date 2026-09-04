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
      slide.data.panels.forEach(function (panel) {
        var total = panel.shares.reduce(function (sum, value) { return sum + value; }, 0);
        var common = panel.shares[0] / total * 100;
        var recurrent = (panel.shares[0] + panel.shares[1]) / total * 100;
        var article = document.createElement("article");
        article.className = "accessibility-panel";
        article.setAttribute("data-accessibility-panel", panel.id);
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
        var bar = document.createElement("div");
        bar.className = "accessibility-signal";
        ["common", "depth", "inaccessible"].forEach(function (kind, index) {
          var segment = document.createElement("span");
          segment.className = "accessibility-segment segment-" + kind;
          segment.style.flexGrow = String(panel.shares[index]);
          bar.appendChild(segment);
        });
        target.appendChild(bar);
        article.appendChild(target);
        var reaches = document.createElement("div");
        reaches.className = "accessibility-reaches";
        var b4 = document.createElement("div");
        b4.className = "accessibility-reach-row reach-b4";
        b4.appendChild(editableText(slide, panel.b4Fit, "span", "accessibility-reach-label"));
        var b4Line = document.createElement("span");
        b4Line.className = "accessibility-reach-line";
        b4.appendChild(b4Line);
        reaches.appendChild(b4);
        var r3 = document.createElement("div");
        r3.className = "accessibility-reach-row reach-r3";
        r3.appendChild(editableText(slide, panel.r3Fit, "span", "accessibility-reach-label"));
        var r3Line = document.createElement("span");
        r3Line.className = "accessibility-reach-line";
        r3.appendChild(r3Line);
        reaches.appendChild(r3);
        article.appendChild(reaches);
        panels.appendChild(article);
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
    }

    function mechanismPipeline(canvas, slide) {
      var body = document.createElement("div");
      body.className = "recipe-body diagram-body";
      var plane = document.createElement("div");
      plane.className = "diagram-plane";
      var paperHost = document.createElement("div");
      paperHost.className = "joint-paper";
      plane.appendChild(paperHost);
      var nodeLabels = {};
      var edgeLabels = {};
      slide.data.nodes.forEach(function (node) {
        var block = document.createElement("div");
        block.className = "diagram-node-copy tone-" + (node.tone || "quiet");
        block.setAttribute("data-diagram-node-id", node.id);
        block.appendChild(editableText(slide, node.label, "div", "node-label"));
        if (node.detail) block.appendChild(editableText(slide, node.detail, "div", "node-detail"));
        nodeLabels[node.id] = block;
        plane.appendChild(block);
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
            // Keep one text-line rounding gutter after scaling. Chromium's
            // line boxes can gain 1–3 px when the fitted group is painted at
            // a fractional scale even though intrinsic measurement is exact.
            height: Math.ceil(Math.max(96, measuredHeight + 16))
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
          onNodePosition: function (id, box, size) {
            var node = nodeLabels[id];
            if (!node) return;
            var fitScale = size.scale || 1;
            node.style.left = (box.x / size.width * 100) + "%";
            node.style.top = (box.y / size.height * 100) + "%";
            node.style.width = (box.width / fitScale / size.width * 100) + "%";
            node.style.height = (box.height / fitScale / size.height * 100) + "%";
            node.style.transform = "scale(" + fitScale + ")";
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
        window.ScientificGeometryRuntime.renderVectorPlane(board, slide.data);
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

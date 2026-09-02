/* Canonical scientific compositions. The editor injects semantic leaf helpers. */
(function (global) {
  "use strict";

  global.createScientificSlideRecipes = function (api) {
    var svgElement = api.svgElement;
    var editableText = api.editableText;
    var galleryImage = api.galleryImage;

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
      var body = document.createElement("div");
      body.className = "recipe-body table-body";
      var table = document.createElement("table");
      table.className = "evidence-table";
      var head = document.createElement("thead");
      var headRow = document.createElement("tr");
      slide.data.columns.forEach(function (componentId) {
        var th = document.createElement("th");
        th.appendChild(editableText(slide, componentId, "div", "table-heading"));
        headRow.appendChild(th);
      });
      head.appendChild(headRow);
      table.appendChild(head);
      var tbody = document.createElement("tbody");
      slide.data.rows.forEach(function (row) {
        var tr = document.createElement("tr");
        var label = document.createElement("th");
        label.scope = "row";
        label.appendChild(editableText(slide, row.label, "div", "table-row-label"));
        tr.appendChild(label);
        row.cells.forEach(function (componentId, index) {
          var td = document.createElement("td");
          if (index === row.best) td.classList.add("row-best");
          if (index === row.globalBest) td.classList.add("global-best");
          td.appendChild(editableText(slide, componentId, "div", "table-value"));
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      body.appendChild(table);
      canvas.appendChild(body);
    }

    function mechanismDiagram(canvas, slide) {
      var body = document.createElement("div");
      body.className = "recipe-body diagram-body";
      var plane = document.createElement("div");
      plane.className = "diagram-plane";
      var svg = svgElement("svg", {viewBox: "0 0 1000 500", "aria-hidden": "true"});
      var defs = svgElement("defs");
      var marker = svgElement("marker", {id: "arrow", viewBox: "0 0 10 10", refX: "9", refY: "5", markerWidth: "14", markerHeight: "14", orient: "auto-start-reverse", markerUnits: "userSpaceOnUse"});
      marker.appendChild(svgElement("path", {d: "M 0 0 L 10 5 L 0 10 z", fill: "context-stroke"}));
      defs.appendChild(marker);
      svg.appendChild(defs);
      var positions = {
        origin: {x: 10, y: 62}, raw: {x: 29, y: 28}, base: {x: 29, y: 76},
        tangent: {x: 57, y: 28}, result: {x: 82, y: 54}
      };
      var labelLanes = {
        "raw>tangent": {x: 43, y: 13},
        "base>tangent": {x: 43, y: 56},
        "tangent>result": {x: 72, y: 14}
      };
      var nodes = {};
      slide.data.nodes.forEach(function (node) { nodes[node.id] = Object.assign({}, node, positions[node.role]); });
      slide.data.edges.forEach(function (edge) {
        var from = nodes[edge.from], to = nodes[edge.to];
        var x1 = from.x * 10, y1 = from.y * 5, x2 = to.x * 10, y2 = to.y * 5;
        var dx = x2 - x1, dy = y2 - y1, length = Math.max(1, Math.sqrt(dx * dx + dy * dy));
        var inset = 70;
        x1 += dx / length * inset; y1 += dy / length * inset;
        x2 -= dx / length * inset; y2 -= dy / length * inset;
        svg.appendChild(svgElement("line", {
          x1: x1, y1: y1, x2: x2, y2: y2, stroke: edge.color || "#8b98aa",
          "stroke-width": "6", "stroke-linecap": "round",
          "stroke-dasharray": edge.dash ? "12 11" : "none",
          "marker-end": edge.directed ? "url(#arrow)" : "none"
        }));
        if (edge.label) {
          var edgeLabel = editableText(slide, edge.label, "div", "edge-label");
          var lane = labelLanes[from.role + ">" + to.role];
          edgeLabel.style.left = (lane ? lane.x : (from.x + to.x) / 2) + "%";
          edgeLabel.style.top = (lane ? lane.y : (from.y + to.y) / 2) + "%";
          plane.appendChild(edgeLabel);
        }
      });
      plane.appendChild(svg);
      slide.data.nodes.forEach(function (node) {
        var position = positions[node.role];
        var block = document.createElement("div");
        block.className = "diagram-node tone-" + (node.tone || "quiet");
        block.style.left = position.x + "%";
        block.style.top = position.y + "%";
        block.appendChild(editableText(slide, node.label, "div", "node-label"));
        plane.appendChild(block);
      });
      body.appendChild(plane);
      canvas.appendChild(body);
    }

    function matchedGallery(canvas, slide) {
      var body = document.createElement("div");
      body.className = "recipe-body gallery-body";
      var grid = document.createElement("div");
      grid.className = "gallery-grid";
      var corner = document.createElement("div");
      corner.className = "gallery-corner";
      grid.appendChild(corner);
      slide.data.columns.forEach(function (componentId) {
        grid.appendChild(editableText(slide, componentId, "div", "gallery-heading"));
      });
      slide.data.rows.forEach(function (row) {
        grid.appendChild(editableText(slide, row.label, "div", "gallery-row-label"));
        row.images.forEach(function (componentId) { grid.appendChild(galleryImage(slide, componentId)); });
      });
      body.appendChild(grid);
      canvas.appendChild(body);
    }

    return {
      "hero-plot": heroPlot,
      "evidence-table": evidenceTable,
      "mechanism-diagram": mechanismDiagram,
      "matched-gallery": matchedGallery
    };
  };
}(window));

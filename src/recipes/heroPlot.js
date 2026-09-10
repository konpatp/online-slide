// Recipe owns layout; injected editor capabilities own mutable state.
export function createHeroPlot(api) {
const global = window;
const {svgElement,editableText} = api;
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


return heroPlot;
}

import JXG from "jsxgraph";
import katex from "katex";
import "../node_modules/jsxgraph/distrib/jsxgraph.css";
import "katex/dist/katex.min.css";

function renderLatex(host, source, options = {}) {
  katex.render(source, host, {
    displayMode: Boolean(options.displayMode),
    throwOnError: false,
    strict: "warn",
    trust: false,
  });
  host.dataset.mathEngine = "katex";
}

function vectorAttributes(item, arrow) {
  const attributes = {
    name: "",
    withLabel: false,
    strokeColor: item.color || "#687991",
    strokeWidth: item.width || 5,
    dash: item.dash ? 2 : 0,
    fixed: true,
    highlight: false,
    layer: item.layer || 4,
  };
  if (arrow) attributes.lastArrow = { type: 2, size: item.arrowSize || 4 };
  return attributes;
}

function renderVectorPlane(host, spec) {
  if (!host.id) host.id = "vector-plane-" + Math.random().toString(36).slice(2);
  const board = JXG.JSXGraph.initBoard(host.id, {
    boundingbox: spec.bounds,
    axis: false,
    keepaspectratio: true,
    showNavigation: false,
    showCopyright: false,
    pan: { enabled: false },
    zoom: { enabled: false },
    renderer: "svg",
  });

  (spec.vectors || []).forEach((item) => {
    board.create("arrow", [item.from, item.to], vectorAttributes(item, true));
  });
  (spec.segments || []).forEach((item) => {
    board.create("segment", [item.from, item.to], vectorAttributes(item, false));
  });
  (spec.arcs || []).forEach((item) => {
    const count = 36;
    const start = item.startDeg * Math.PI / 180;
    const end = item.endDeg * Math.PI / 180;
    const xs = [];
    const ys = [];
    for (let index = 0; index <= count; index += 1) {
      const angle = start + (end - start) * index / count;
      xs.push(item.center[0] + item.radius * Math.cos(angle));
      ys.push(item.center[1] + item.radius * Math.sin(angle));
    }
    board.create("curve", [xs, ys], vectorAttributes(item, false));
  });
  (spec.points || []).forEach((item) => {
    board.create("point", item.at, {
      name: "",
      withLabel: false,
      size: item.size || 3,
      face: "o",
      fillColor: item.color || "#14233b",
      strokeColor: item.color || "#14233b",
      fixed: true,
      highlight: false,
      layer: item.layer || 6,
    });
  });

  host.dataset.geometryEngine = "jsxgraph";
  host.dataset.geometryVectors = String((spec.vectors || []).length);
  return board;
}

window.ScientificMathRuntime = { renderLatex };
window.ScientificGeometryRuntime = { renderVectorPlane };

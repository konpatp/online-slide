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

function rounded(value) {
  return Math.round(value * 10000) / 10000;
}

function renderVectorPlane(host, spec, options = {}) {
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

  const controls = new Map();
  let selectedId = options.selectedId || null;
  const [leftBound, topBound, rightBound, bottomBound] = spec.bounds;

  function handleAttributes(kind) {
    return {
      name: "",
      withLabel: false,
      size: kind === "center" ? 4.5 : 5,
      face: kind === "center" ? "[]" : "o",
      fillColor: kind === "center" ? "#ffffff" : "#2f6fed",
      strokeColor: "#2f6fed",
      strokeWidth: 3,
      fixed: false,
      highlight: true,
      highlightFillColor: "#eaf1ff",
      highlightStrokeColor: "#173e8c",
      layer: 12,
      visible: false,
      showInfobox: false,
    };
  }

  function pointValue(point) {
    const x = Math.max(leftBound, Math.min(rightBound, point.X()));
    const y = Math.max(bottomBound, Math.min(topBound, point.Y()));
    if (x !== point.X() || y !== point.Y()) {
      point.setPositionDirectly(JXG.COORDS_BY_USER, [x, y]);
    }
    return [rounded(x), rounded(y)];
  }

  function setSelected(id, kind) {
    selectedId = id;
    controls.forEach((control, key) => {
      const visible = key === selectedId;
      control.handles.forEach((handle) => handle.setAttribute({ visible }));
    });
    board.update();
    if (options.onSelect) options.onSelect(kind, id);
  }

  function createEditableLinear(item, kind, arrow) {
    const persisted = (options.objects || {})[item.id];
    const from = persisted && persisted.kind === kind ? persisted.from : item.from;
    const to = persisted && persisted.kind === kind ? persisted.to : item.to;
    if (!(options.interactive && item.editable === true)) {
      return board.create(arrow ? "arrow" : "segment", [from, to], vectorAttributes(item, arrow));
    }
    const start = board.create("point", from, handleAttributes("endpoint"));
    const end = board.create("point", to, handleAttributes("endpoint"));
    const center = board.create("point", [
      (from[0] + to[0]) / 2,
      (from[1] + to[1]) / 2,
    ], handleAttributes("center"));
    const linear = board.create(arrow ? "arrow" : "segment", [start, end], vectorAttributes(item, arrow));
    const control = { item, kind, linear, start, end, center, handles: [start, end, center], movingCenter: false };
    controls.set(item.id, control);

    function geometry() {
      return { from: pointValue(start), to: pointValue(end) };
    }

    function syncCenter() {
      if (control.movingCenter) return;
      const a = pointValue(start);
      const b = pointValue(end);
      center.setPositionDirectly(JXG.COORDS_BY_USER, [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]);
      board.update();
    }

    function emit(commit) {
      if (options.onObjectChange) options.onObjectChange(kind, item.id, geometry(), commit);
    }

    [start, end].forEach((handle) => {
      handle.on("down", () => setSelected(item.id, kind));
      handle.on("drag", () => { syncCenter(); emit(false); });
      handle.on("up", () => { syncCenter(); emit(true); });
    });

    let previousCenter = pointValue(center);
    center.on("down", () => {
      previousCenter = pointValue(center);
      control.movingCenter = true;
      setSelected(item.id, kind);
    });
    center.on("drag", () => {
      const nextCenter = pointValue(center);
      const dx = nextCenter[0] - previousCenter[0];
      const dy = nextCenter[1] - previousCenter[1];
      const a = pointValue(start);
      const b = pointValue(end);
      start.setPositionDirectly(JXG.COORDS_BY_USER, [a[0] + dx, a[1] + dy]);
      end.setPositionDirectly(JXG.COORDS_BY_USER, [b[0] + dx, b[1] + dy]);
      previousCenter = nextCenter;
      board.update();
      emit(false);
    });
    center.on("up", () => {
      control.movingCenter = false;
      emit(true);
    });
    linear.on("down", () => setSelected(item.id, kind));
    return linear;
  }

  (spec.vectors || []).forEach((item) => {
    createEditableLinear(item, "vector", true);
  });
  (spec.segments || []).forEach((item) => {
    createEditableLinear(item, "segment", false);
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
  host.dataset.geometryEditableObjects = String(controls.size);
  if (selectedId && controls.has(selectedId)) {
    const control = controls.get(selectedId);
    setSelected(selectedId, control.kind);
  }
  host.__scientificGeometry = { board, controls, select: setSelected };
  return board;
}

window.ScientificMathRuntime = { renderLatex };
window.ScientificGeometryRuntime = { renderVectorPlane };

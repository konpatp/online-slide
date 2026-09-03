import { dia, shapes } from "@joint/core";
import { DirectedGraph } from "@joint/layout-directed-graph";

const PALETTE = {
  quiet: { fill: "#f7f9fc", stroke: "#c8d2df" },
  teacher: { fill: "#edf3ff", stroke: "#7aa2ef" },
  student: { fill: "#fff3ea", stroke: "#e19a65" },
  output: { fill: "#edf9f4", stroke: "#66bda5" },
  result: { fill: "#f5f0fb", stroke: "#a88ad3" },
};

function renderPipeline(host, spec, options = {}) {
  const graph = new dia.Graph({}, { cellNamespace: shapes });
  const nodeModels = new Map();
  const nodeSpecs = new Map();
  const linkModels = new Map();
  const width = Math.max(900, host.clientWidth || 1200);
  const height = Math.max(360, host.clientHeight || 480);

  spec.nodes.forEach((node) => {
    const tone = PALETTE[node.tone] || PALETTE.quiet;
    const rect = new shapes.standard.Rectangle({ id: node.id });
    rect.resize(node.layoutWidth || node.width || 220, node.layoutHeight || node.height || 96);
    rect.attr({
      body: {
        fill: tone.fill,
        stroke: tone.stroke,
        strokeWidth: node.emphasis ? 4 : 2.5,
        rx: 20,
        ry: 20,
      },
      label: { text: "" },
    });
    rect.set("z", 2);
    nodeModels.set(node.id, rect);
    nodeSpecs.set(node.id, node);
    graph.addCell(rect);
  });

  spec.edges.forEach((edge) => {
    const link = new shapes.standard.Link({ id: edge.id });
    link.source({ id: edge.from });
    link.target({ id: edge.to });
    link.attr({
      line: {
        stroke: edge.color || "#8b98aa",
        strokeWidth: edge.emphasis ? 5.5 : 4.5,
        strokeDasharray: edge.dash ? "12 10" : "none",
        strokeLinecap: "round",
        strokeLinejoin: "round",
        targetMarker: {
          type: "path",
          d: "M 10 -5 0 0 10 5 z",
          fill: edge.color || "#8b98aa",
          stroke: "none",
        },
      },
    });
    link.router("manhattan", { padding: 30, step: 10, maximumLoops: 900 });
    link.connector("rounded", { radius: 14 });
    link.set("z", 1);
    linkModels.set(edge.id, link);
    graph.addCell(link);
  });

  let scale = 1;

  function centerAndFit(bounds) {
    const paddingX = 54;
    const paddingY = 42;
    scale = Math.min(
      1,
      (width - paddingX * 2) / bounds.width,
      (height - paddingY * 2) / bounds.height,
    );
    graph.getElements().forEach((element) => {
      const box = element.getBBox();
      element.resize(box.width * scale, box.height * scale);
      element.position(
        (box.x - bounds.x) * scale + (width - bounds.width * scale) / 2,
        (box.y - bounds.y) * scale + (height - bounds.height * scale) / 2,
      );
    });
  }

  function layoutLanes() {
    const natural = [...nodeModels.entries()].map(([id, model]) => ({
      id,
      model,
      spec: nodeSpecs.get(id),
      box: model.getBBox(),
    }));
    const lanes = natural.map((item) => item.spec.lane);
    const steps = natural.map((item) => item.spec.step);
    const minLane = Math.floor(Math.min(...lanes));
    const maxLane = Math.ceil(Math.max(...lanes));
    const orderedSteps = [...new Set(steps)].sort((left, right) => left - right);
    const stepWidths = new Map(orderedSteps.map((step) => [
      step,
      Math.max(...natural.filter((item) => item.spec.step === step).map((item) => item.box.width)),
    ]));
    const stepStarts = new Map();
    let nextStepStart = 0;
    orderedSteps.forEach((step, index) => {
      stepStarts.set(step, nextStepStart);
      nextStepStart += stepWidths.get(step);
      if (index < orderedSteps.length - 1) nextStepStart += spec.rankGap || 90;
    });
    const laneHeights = new Map();
    for (let lane = minLane; lane <= maxLane; lane += 1) {
      const exact = natural.filter((item) => item.spec.lane === lane).map((item) => item.box.height);
      laneHeights.set(lane, exact.length ? Math.max(...exact) : 96);
    }
    const laneCenters = new Map();
    let laneCursor = 0;
    for (let lane = minLane; lane <= maxLane; lane += 1) {
      const laneHeight = laneHeights.get(lane);
      laneCenters.set(lane, laneCursor + laneHeight / 2);
      laneCursor += laneHeight;
      if (lane < maxLane) laneCursor += spec.nodeGap || 52;
    }
    function laneCenter(lane) {
      if (Number.isInteger(lane)) return laneCenters.get(lane);
      const lower = Math.floor(lane);
      const upper = Math.ceil(lane);
      const ratio = lane - lower;
      return laneCenters.get(lower) * (1 - ratio) + laneCenters.get(upper) * ratio;
    }
    const placements = natural.map((item) => ({
      item,
      x: stepStarts.get(item.spec.step) + (stepWidths.get(item.spec.step) - item.box.width) / 2,
      y: laneCenter(item.spec.lane) - item.box.height / 2,
    }));
    const minY = Math.min(...placements.map((entry) => entry.y));
    const maxY = Math.max(...placements.map((entry) => entry.y + entry.item.box.height));
    const bounds = {
      x: 0,
      y: minY,
      width: nextStepStart,
      height: maxY - minY,
    };
    const paddingX = 54;
    const paddingY = 42;
    scale = Math.min(
      1,
      (width - paddingX * 2) / bounds.width,
      (height - paddingY * 2) / bounds.height,
    );
    const offsetX = (width - bounds.width * scale) / 2;
    const offsetY = (height - bounds.height * scale) / 2;
    placements.forEach(({ item, x, y }) => {
      item.model.resize(item.box.width * scale, item.box.height * scale);
      item.model.position(
        x * scale + offsetX,
        (y - bounds.y) * scale + offsetY,
      );
    });
  }

  function layoutGraph() {
    if (spec.layout === "lanes") {
      layoutLanes();
    } else {
      DirectedGraph.layout(graph, {
        rankDir: spec.direction || "LR",
        nodeSep: spec.nodeGap || 62,
        rankSep: spec.rankGap || 110,
        edgeSep: 38,
        marginX: 54,
        marginY: 42,
        setLinkVertices: false,
      });
      centerAndFit(graph.getCellsBBox(graph.getElements()));
    }
    graph.getLinks().forEach((link) => link.vertices([]));
    host.dataset.diagramScale = scale.toFixed(4);
  }

  layoutGraph();

  const paper = new dia.Paper({
    el: host,
    model: graph,
    width,
    height,
    gridSize: 1,
    cellViewNamespace: shapes,
    background: { color: "transparent" },
    interactive: () => Boolean(options.interactive),
  });

  function publishPositions() {
    if (options.onNodePosition) {
      nodeModels.forEach((model, id) => options.onNodePosition(
        id, model.getBBox(), { width, height, scale },
      ));
    }
    if (options.onEdgePosition) {
      linkModels.forEach((model, id) => {
        const view = paper.findViewByModel(model);
        if (!view || !view.getConnection()) return;
        const path = view.getConnection();
        const length = typeof path.length === "function" ? path.length() : 0;
        const pointAtLength = typeof path.pointAtLength === "function"
          ? path.pointAtLength.bind(path)
          : (typeof path.getPointAtLength === "function" ? path.getPointAtLength.bind(path) : null);
        // During a batched content refit JointJS may emit render:done before
        // a link's connection path is complete. Node geometry is already
        // valid; defer the optional edge label rather than aborting the
        // remaining node resize operations.
        if (!pointAtLength || !length) return;
        options.onEdgePosition(id, pointAtLength(length / 2), { width, height });
      });
    }
  }

  function resizeNodes(sizes) {
    // Treat intrinsic remeasurement plus the resulting track fit as one
    // atomic graph update. Without the batch, JointJS may paint the temporary
    // unscaled sizes between model.resize() and layoutGraph(); the editor can
    // then retain those intermediate boxes even though the final positions
    // were computed at the fitted scale.
    graph.startBatch("content-fit");
    try {
      Object.keys(sizes).forEach((id) => {
        const model = nodeModels.get(id);
        const size = sizes[id];
        if (!model || !size) return;
        model.resize(size.width, size.height);
      });
      layoutGraph();
    } finally {
      graph.stopBatch("content-fit");
    }
    paper.updateViews();
    requestAnimationFrame(publishPositions);
  }
  paper.on("element:pointermove", publishPositions);
  paper.on("render:done", publishPositions);
  requestAnimationFrame(publishPositions);

  host.dataset.diagramEngine = "jointjs-directed-graph";
  host.dataset.diagramScale = scale.toFixed(4);
  host.dataset.diagramNodes = String(spec.nodes.length);
  host.dataset.diagramEdges = String(spec.edges.length);
  host.dataset.diagramContentSizing = "measured";
  host.dataset.diagramLayout = spec.layout || "directed";
  // Read-only handle used by the browser acceptance gate to compare the
  // semantic layout model with its painted SVG/HTML representations.
  host.__scientificDiagram = { graph, paper };
  return { graph, paper, publishPositions, resizeNodes };
}

window.ScientificDiagramRuntime = { renderPipeline };

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
  const linkModels = new Map();
  const width = Math.max(900, host.clientWidth || 1200);
  const height = Math.max(360, host.clientHeight || 480);

  spec.nodes.forEach((node) => {
    const tone = PALETTE[node.tone] || PALETTE.quiet;
    const rect = new shapes.standard.Rectangle({ id: node.id });
    rect.resize(node.width || 220, node.height || 96);
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

  DirectedGraph.layout(graph, {
    rankDir: spec.direction || "LR",
    nodeSep: spec.nodeGap || 62,
    rankSep: spec.rankGap || 110,
    edgeSep: 38,
    marginX: 54,
    marginY: 42,
    setLinkVertices: false,
  });
  graph.getLinks().forEach((link) => link.vertices([]));

  const bounds = graph.getCellsBBox(graph.getElements());
  const paddingX = 54;
  const paddingY = 42;
  const scale = Math.min(
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
      nodeModels.forEach((model, id) => options.onNodePosition(id, model.getBBox(), { width, height }));
    }
    if (options.onEdgePosition) {
      linkModels.forEach((model, id) => {
        const view = paper.findViewByModel(model);
        if (!view || !view.getConnection()) return;
        const path = view.getConnection();
        options.onEdgePosition(id, path.getPointAtLength(path.length() / 2), { width, height });
      });
    }
  }
  paper.on("element:pointermove", publishPositions);
  paper.on("render:done", publishPositions);
  requestAnimationFrame(publishPositions);

  host.dataset.diagramEngine = "jointjs-directed-graph";
  host.dataset.diagramScale = scale.toFixed(4);
  host.dataset.diagramNodes = String(spec.nodes.length);
  host.dataset.diagramEdges = String(spec.edges.length);
  return { graph, paper, publishPositions };
}

window.ScientificDiagramRuntime = { renderPipeline };

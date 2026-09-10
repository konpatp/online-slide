// Recipe owns layout; injected editor capabilities own mutable state.
export function createMechanismPipeline(api) {
const global = window;
const {editableText,fitGroupInRegion,objectsForSlide,selectedObjectId,selectVisualObject,updateVisualObject} = api;
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
    if (!plane.isConnected) return;
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


return mechanismPipeline;
}

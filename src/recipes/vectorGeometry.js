// Recipe owns layout; injected editor capabilities own mutable state.
export function createVectorGeometry(api) {
const global = window;
const {editableText,bindTextRegion,effectiveComponent,objectsForSlide,selectedObjectId,selectVisualObject,updateVisualObject} = api;
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
    if (!board.isConnected) return;
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


return vectorGeometry;
}

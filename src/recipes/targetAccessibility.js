// Recipe owns layout; injected editor capabilities own mutable state.
export function createTargetAccessibility(api) {
const global = window;
const {editableText,wireVisualObjects} = api;
function targetAccessibility(canvas, slide) {
  var body = document.createElement("div");
  body.className = "recipe-body accessibility-body";
  var panels = document.createElement("div");
  panels.className = "accessibility-panels";
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

  wireVisualObjects(slide,records);
}

// One bounded drag/resize implementation for authored shapes and recipe
// marks. Coordinates belong to the owning plane, never the viewport.

return targetAccessibility;
}

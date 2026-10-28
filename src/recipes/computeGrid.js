// Equal-compute blocks: each tile is one network pass over one image. A row is one image's
// chain of passes; red nodes are supervised states, hollow nodes are the model's own.
const SVG = 'http://www.w3.org/2000/svg';
const SCALE = 1.2, STEP = 118, NODE = 13, TILE_H = 50, ROW = 66, PAD = 18;

export function createComputeGrid(api, trackPanel) {
const {editableText} = api;

function svgNode(name, attributes) {
  var node = document.createElementNS(SVG, name);
  Object.keys(attributes).forEach(function (key) { node.setAttribute(key, attributes[key]); });
  return node;
}

function block(slide, spec) {
  var host = document.createElement('section');
  host.className = 'cg-block';
  var head = document.createElement('div');
  head.className = 'cg-head';
  head.appendChild(editableText(slide, spec.title, 'div', 'cg-title'));
  head.appendChild(editableText(slide, spec.subtitle, 'div', 'cg-subtitle'));
  host.appendChild(head);
  var width = 2 * PAD + spec.tiles * STEP, height = spec.rows * ROW;
  var svg = svgNode('svg', {viewBox: '0 0 ' + width + ' ' + height, class: 'cg-svg', role: 'img', width: width * SCALE, height: height * SCALE});
  for (var r = 0; r < spec.rows; r++) {
    var y = r * ROW + ROW / 2;
    var node = function (k) { return PAD + k * STEP; };
    svg.appendChild(svgNode('line', {class: 'cg-line', x1: node(0), x2: node(spec.tiles), y1: y, y2: y}));
    // Supervision: one span across the whole row, or one span per pass.
    if (spec.supervision === 'span') {
      svg.appendChild(svgNode('line', {class: 'cg-line supervised', x1: node(0), x2: node(spec.tiles), y1: y, y2: y}));
    } else {
      for (var j = 0; j < spec.tiles; j++) svg.appendChild(svgNode('line', {class: 'cg-line supervised', x1: node(j), x2: node(j + 1), y1: y, y2: y}));
    }
    for (var k = 0; k < spec.tiles; k++) {
      svg.appendChild(svgNode('rect', {class: 'cg-tile', x: node(k) + NODE + 6, y: y - TILE_H / 2, width: STEP - 2 * NODE - 12, height: TILE_H, rx: 9}));
    }
    for (k = 0; k <= spec.tiles; k++) {
      // Only supervised states are solid red; the states between a looped row's passes are its own.
      var supervised = spec.supervision === 'each' || k === 0 || k === spec.tiles;
      svg.appendChild(svgNode('circle', {class: 'cg-node' + (supervised ? ' supervised' : ''), cx: node(k), cy: y, r: NODE}));
    }
  }
  host.appendChild(svg);
  if (spec.caption) host.appendChild(editableText(slide, spec.caption, 'div', 'cg-caption'));
  return host;
}

function computeGrid(canvas, slide) {
  var data = slide.data;
  var body = document.createElement('div');
  body.className = 'recipe-body compute-grid-body';
  if (data.intuition) {
    var strip = document.createElement('div');
    strip.className = 'cg-intuition';
    strip.appendChild(trackPanel(slide, {units: data.intuition.units}, data.intuition.panel));
    if (data.intuition.caption) strip.appendChild(editableText(slide, data.intuition.caption, 'div', 'cg-intuition-caption'));
    body.appendChild(strip);
  }
  var blocks = document.createElement('div');
  blocks.className = 'cg-blocks';
  data.blocks.forEach(function (spec, index) {
    if (index) {
      var sign = document.createElement('div');
      sign.className = 'cg-versus';
      sign.appendChild(editableText(slide, data.versus, 'div', 'cg-versus-text'));
      blocks.appendChild(sign);
    }
    blocks.appendChild(block(slide, spec));
  });
  body.appendChild(blocks);
  var notes = document.createElement('div');
  notes.className = 'cg-notes';
  data.notes.forEach(function (parts) {
    var line = document.createElement('div');
    line.className = 'cg-note';
    parts.forEach(function (component) { line.appendChild(editableText(slide, component, 'span', 'cg-note-part')); });
    notes.appendChild(line);
  });
  body.appendChild(notes);
  canvas.appendChild(body);
}
return computeGrid;
}

// Stacked tracks of states over one shared position axis: a teacher rollout above a student
// path, dashed links where a teacher state feeds or checks a student state, and a bracket.
// Recipe owns geometry; the slide declares positions, spans and text.
const SVG = 'http://www.w3.org/2000/svg';
const WIDTH = 1000, HEIGHT = 192, PAD = 30;
const TEACHER_Y = 20, STUDENT_Y = 86, BRACKET_Y = 140;

export function createTrackDiagram(api) {
const {editableText} = api;

function svgNode(name, attributes) {
  var node = document.createElementNS(SVG, name);
  Object.keys(attributes).forEach(function (key) { node.setAttribute(key, attributes[key]); });
  return node;
}

function panel(slide, data, spec) {
  var step = (WIDTH - 2 * PAD) / data.units;
  var x = function (position) { return PAD + position * step; };
  var block = document.createElement('section');
  block.className = 'track-panel';
  var title = document.createElement('div');
  title.className = 'track-title';
  title.appendChild(editableText(slide, spec.title, 'div', 'track-title-text'));
  var names = document.createElement('div');
  names.className = 'track-names';
  var canvas = document.createElement('div');
  canvas.className = 'track-canvas';
  var svg = svgNode('svg', {viewBox: '0 0 ' + WIDTH + ' ' + HEIGHT, class: 'track-svg', role: 'img'});
  var place = function (host, y, text) {
    var label = editableText(slide, text, 'div', 'track-name');
    label.style.top = (y / HEIGHT * 100) + '%';
    host.appendChild(label);
  };
  var teacher = spec.teacher, student = spec.student;
  // Links first, so nodes sit on top of them.
  (spec.links || []).forEach(function (position) {
    svg.appendChild(svgNode('line', {class: 'track-link', x1: x(position), x2: x(position), y1: TEACHER_Y + 12, y2: STUDENT_Y - 18}));
  });
  var nodes = teacher.nodes;
  for (var i = 0; i + 1 < nodes.length; i++) {
    svg.appendChild(svgNode('line', {class: 'track-teacher-line', x1: x(nodes[i]), x2: x(nodes[i + 1]), y1: TEACHER_Y, y2: TEACHER_Y}));
  }
  nodes.forEach(function (position) { svg.appendChild(svgNode('circle', {class: 'track-teacher-node', cx: x(position), cy: TEACHER_Y, r: 11})); });
  var last = student.nodes.length - 1;
  svg.appendChild(svgNode('line', {class: 'track-student-line', x1: x(student.nodes[0]), x2: x(student.nodes[last]), y1: STUDENT_Y, y2: STUDENT_Y}));
  var supervised = new Set();
  (student.supervised || []).forEach(function (span) {
    svg.appendChild(svgNode('line', {class: 'track-student-line supervised', x1: x(span[0]), x2: x(span[1]), y1: STUDENT_Y, y2: STUDENT_Y}));
    supervised.add(span[0]); supervised.add(span[1]);
  });
  student.nodes.forEach(function (position) {
    svg.appendChild(svgNode('circle', {class: 'track-student-node' + (supervised.has(position) ? ' supervised' : ''), cx: x(position), cy: STUDENT_Y, r: 15}));
  });
  if (spec.bracket) {
    var a = x(spec.bracket.from), b = x(spec.bracket.to);
    svg.appendChild(svgNode('path', {class: 'track-bracket', d: 'M' + a + ' ' + (BRACKET_Y - 9) + ' V' + BRACKET_Y + ' H' + b + ' V' + (BRACKET_Y - 9)}));
  }
  canvas.appendChild(svg);
  var overlay = function (component, left, y, className) {
    var label = editableText(slide, component, 'div', className);
    label.style.left = (left * 100) + '%';
    label.style.top = (y / HEIGHT * 100) + '%';
    canvas.appendChild(label);
  };
  if (spec.bracket) overlay(spec.bracket.label, (x(spec.bracket.from) + x(spec.bracket.to)) / 2 / WIDTH, BRACKET_Y + 30, 'track-bracket-label');
  (spec.nodeLabels || []).forEach(function (item) { overlay(item.label, x(item.at) / WIDTH, STUDENT_Y + 34, 'track-node-label'); });
  place(names, TEACHER_Y, teacher.label);
  place(names, STUDENT_Y, student.label);
  block.append(title, names, canvas);
  return block;
}

function trackDiagram(canvas, slide) {
  var data = slide.data;
  var body = document.createElement('div');
  body.className = 'recipe-body track-diagram-body';
  data.panels.forEach(function (spec) { body.appendChild(panel(slide, data, spec)); });
  if (data.footer) {
    var footer = document.createElement('div');
    footer.className = 'track-footer';
    data.footer.forEach(function (component) { footer.appendChild(editableText(slide, component, 'div', 'track-footer-part')); });
    body.appendChild(footer);
  }
  canvas.appendChild(body);
}
return trackDiagram;
}

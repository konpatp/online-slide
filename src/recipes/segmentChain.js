// A chain of states with highlighted segments. Recipe owns the geometry and the
// one-shot Play; the slide declares only nodes, segments to highlight and text.
const SVG = 'http://www.w3.org/2000/svg';
const WIDTH = 1000, HEIGHT = 72, PAD = 34, RADIUS = 17, HEAD = 24;

export function createSegmentChain(api) {
const {editableText, effectiveComponent} = api;

function svgNode(name, attributes) {
  var node = document.createElementNS(SVG, name);
  Object.keys(attributes).forEach(function (key) { node.setAttribute(key, attributes[key]); });
  return node;
}

function buildRow(slide, data, row) {
  var count = data.nodes, step = (WIDTH - 2 * PAD) / (count - 1);
  var x = function (index) { return PAD + index * step; };
  var track = document.createElement('div');
  track.className = 'chain-track' + (data.edgeLabel ? ' with-edge-labels' : '') + ((row.nodeLabels || []).length ? ' with-node-labels' : '');
  var svg = svgNode('svg', {viewBox: '0 0 ' + WIDTH + ' ' + HEIGHT, class: 'chain-svg', role: 'img', preserveAspectRatio: 'xMidYMid meet'});
  var segments = [], heads = [], dots = [], mid = HEIGHT / 2;
  for (var j = 0; j < count - 1; j++) {
    segments.push(svg.appendChild(svgNode('line', {class: 'chain-seg', x1: x(j) + RADIUS, x2: x(j + 1) - RADIUS, y1: mid, y2: mid})));
  }
  if (data.arrows) for (j = 0; j < count - 1; j++) {
    var tip = x(j + 1) - RADIUS - 8;
    heads.push(svg.appendChild(svgNode('path', {class: 'chain-head', d: 'M' + (tip - HEAD) + ' ' + (mid - HEAD * .6) + ' L' + tip + ' ' + mid + ' L' + (tip - HEAD) + ' ' + (mid + HEAD * .6) + ' Z'})));
  }
  for (var i = 0; i < count; i++) {
    dots.push(svg.appendChild(svgNode('circle', {class: 'chain-dot', cx: x(i), cy: mid, r: RADIUS})));
  }
  track.appendChild(svg);
  var overlay = function (component, index, fraction, className) {
    var label = editableText(slide, component, 'div', className);
    label.style.left = (fraction * 100) + '%';
    track.appendChild(label);
  };
  if (data.edgeLabel) for (j = 0; j < count - 1; j++) overlay(data.edgeLabel, j, (x(j) + x(j + 1)) / 2 / WIDTH, 'chain-edge-label');
  (row.nodeLabels || []).forEach(function (item) { overlay(item.label, item.node, x(item.node) / WIDTH, 'chain-node-label'); });

  var frames = row.frames;
  return {
    element: track,
    show: function (frame) {
      var span = frames[Math.min(frame, frames.length - 1)];
      // Only a span's endpoints are supervised states; the states between them are the model's own.
      dots.forEach(function (dot, index) {
        dot.classList.toggle('supervised', index === span[0] || index === span[1]);
        dot.classList.toggle('interior', index > span[0] && index < span[1]);
      });
      segments.forEach(function (seg, index) {
        var on = index >= span[0] && index < span[1];
        seg.classList.toggle('supervised', on);
        if (heads[index]) heads[index].classList.toggle('supervised', on);
      });
    }
  };
}

function segmentChain(canvas, slide) {
  var data = slide.data;
  var body = document.createElement('div');
  body.className = 'recipe-body segment-chain-body';
  var labelled = !data.play && !data.groups.some(function (group) { return group.rows.some(function (row) { return row.label; }); });
  body.classList.toggle('unlabelled', labelled);
  var rows = [], frameCount = 1;
  var header = document.createElement('div');
  header.className = 'chain-header';
  var controls = document.createElement('div');
  controls.className = 'chain-controls';
  header.appendChild(controls);
  var ends = document.createElement('div');
  ends.className = 'chain-ends';
  if (data.ends) {
    ['first', 'middle', 'last'].forEach(function (key) {
      if (!data.ends[key]) return;
      var end = document.createElement('div');
      end.className = 'chain-end chain-end-' + key;
      [].concat(data.ends[key]).forEach(function (component) { end.appendChild(editableText(slide, component, 'span', 'chain-end-part')); });
      ends.appendChild(end);
    });
  }
  header.appendChild(ends);
  body.appendChild(header);
  data.groups.forEach(function (group) {
    var block = document.createElement('section');
    block.className = 'chain-group';
    // A caption shares the heading's line; without a heading it is a quiet line below the rows.
    if (group.heading) {
      var head = document.createElement('div');
      head.className = 'chain-group-head';
      head.appendChild(editableText(slide, group.heading, 'div', 'chain-heading'));
      if (group.caption) head.appendChild(editableText(slide, group.caption, 'div', 'chain-caption'));
      block.appendChild(head);
    }
    group.rows.forEach(function (rowSpec) {
      var line = document.createElement('div');
      line.className = 'chain-row';
      var label = document.createElement('div');
      label.className = 'chain-row-label';
      if (rowSpec.label) label.appendChild(editableText(slide, rowSpec.label, 'span', 'chain-row-text'));
      line.appendChild(label);
      var row = buildRow(slide, data, rowSpec);
      line.appendChild(row.element);
      block.appendChild(line);
      rows.push(row);
      frameCount = Math.max(frameCount, rowSpec.frames.length);
    });
    if (group.caption && !group.heading) block.appendChild(editableText(slide, group.caption, 'div', 'chain-caption chain-footnote'));
    body.appendChild(block);
  });

  if (data.footnote) body.appendChild(editableText(slide, data.footnote, 'div', 'chain-caption chain-footnote'));
  var counter = document.createElement('output');
  counter.className = 'chain-counter';
  var count = document.createElement('span');
  counter.appendChild(count);
  function show(frame) {
    rows.forEach(function (row) { row.show(frame); });
    count.textContent = ' ' + (frame + 1) + ' / ' + frameCount;
  }
  show(0);
  if (data.play) {
    var button = document.createElement('button');
    button.type = 'button';
    button.className = 'chain-play';
    var running = false, frame = 0, timer = null;
    var caption = function (key) { return '▶ ' + effectiveComponent(slide, data.play[key]).text; };
    button.textContent = caption('label');
    // Presentation keys navigate slides; a focused control keeps Space/Enter for itself.
    button.addEventListener('keydown', function (event) { event.stopPropagation(); });
    button.addEventListener('click', function (event) {
      event.stopPropagation();
      if (running) return;
      running = true; frame = 0; show(0);
      button.disabled = true;
      // One finite sequence, started by this click: it ends at the last frame,
      // or as soon as this slide leaves the document.
      (function advance() {
        timer = setTimeout(function () {
          if (!body.isConnected) { running = false; return; }
          frame += 1; show(frame);
          if (frame < frameCount - 1) { advance(); return; }
          running = false; button.disabled = false; button.textContent = caption('replay');
        }, data.play.intervalMs || 900);
      })();
    });
    controls.appendChild(button);
    counter.insertBefore(editableText(slide, data.play.counter, 'span', 'chain-counter-word'), count);
    controls.appendChild(counter);
  }
  canvas.appendChild(body);
}
return segmentChain;
}

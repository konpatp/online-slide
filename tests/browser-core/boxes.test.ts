import {test} from 'node:test';
import assert from 'node:assert/strict';
import {moveBox, resizeBox, nudgeBox, isDrag, HANDLES} from '../../src/editor/boxes';
import type {Box, Handle} from '../../src/editor/boxes';

const slide: Box = {x: 0, y: 0, width: 1920, height: 1080};
const limits = {bounds: slide, minWidth: 40, minHeight: 20};
const box: Box = {x: 100, y: 100, width: 400, height: 200};
const inside = (b: Box) => b.x >= -1e-9 && b.y >= -1e-9 && b.x + b.width <= 1920 + 1e-9 && b.y + b.height <= 1080 + 1e-9;

test('moves stay on the slide', () => {
  assert.deepEqual(moveBox(box, 50, -20, slide), {...box, x: 150, y: 80});
  assert.deepEqual(moveBox(box, -500, -500, slide), {...box, x: 0, y: 0});
  assert.deepEqual(moveBox(box, 5000, 5000, slide), {...box, x: 1520, y: 880});
});

test('each handle drags exactly its edges and keeps the opposite edge fixed', () => {
  const expect: Record<Handle, Box> = {
    n: {x: 100, y: 90, width: 400, height: 210}, s: {x: 100, y: 100, width: 400, height: 210},
    e: {x: 100, y: 100, width: 410, height: 200}, w: {x: 90, y: 100, width: 410, height: 200},
    ne: {x: 100, y: 90, width: 410, height: 210}, nw: {x: 90, y: 90, width: 410, height: 210},
    se: {x: 100, y: 100, width: 410, height: 210}, sw: {x: 90, y: 100, width: 410, height: 210}};
  for (const handle of HANDLES) {
    const dx = handle.includes('w') ? -10 : 10, dy = handle.includes('n') ? -10 : 10;
    assert.deepEqual(resizeBox(box, handle, dx, dy, limits), expect[handle], handle);
  }
});

test('resizes respect minimum size and the slide edge from every handle', () => {
  for (const handle of HANDLES) for (const d of [-3000, 3000]) {
    const next = resizeBox(box, handle, d, d, limits);
    assert.ok(next.width >= 40 - 1e-9 && next.height >= 20 - 1e-9, handle);
    assert.ok(inside(next), handle + ' ' + d);
  }
});

test('proportional resize keeps the aspect ratio, stays on the slide and anchors correctly', () => {
  for (const handle of HANDLES) for (const d of [-3000, -30, 30, 3000]) {
    const next = resizeBox(box, handle, d, d * .3, limits, true);
    assert.ok(Math.abs(next.width / next.height - 2) < 1e-9, handle);
    assert.ok(inside(next), handle + ' ' + d);
  }
  const grown = resizeBox(box, 'se', 100, 0, limits, true);
  assert.deepEqual([grown.x, grown.y, grown.width, grown.height], [100, 100, 500, 250]);
  const west = resizeBox(box, 'w', -100, 0, limits, true);
  assert.equal(west.x + west.width, 500);
  assert.equal(west.y + west.height / 2, 200);
});

test('proportional corners follow the dominant pointer axis when shrinking and growing', () => {
  const shrink = resizeBox(box, 'se', -100, -2, limits, true);
  assert.equal(shrink.width, 300); assert.equal(shrink.height, 150);
  const grow = resizeBox(box, 'nw', -5, -50, limits, true);
  assert.equal(grow.height, 250); assert.equal(grow.width, 500);
  assert.equal(grow.x + grow.width, 500); assert.equal(grow.y + grow.height, 300);
});

test('nudges are one or ten pixels and ignore other keys', () => {
  assert.deepEqual(nudgeBox(box, 'ArrowRight', false, slide), {...box, x: 101});
  assert.deepEqual(nudgeBox(box, 'ArrowUp', true, slide), {...box, y: 90});
  assert.equal(nudgeBox(box, 'a', false, slide), null);
  assert.deepEqual(nudgeBox({...box, x: 0}, 'ArrowLeft', true, slide), {...box, x: 0});
});

test('small pointer jitter is a click, not a drag', () => {
  assert.equal(isDrag(2, 2), false);
  assert.equal(isDrag(3, 3), true);
});

import {snapMove, snapResize, alignBoxes, distributeBoxes, scaleGroup, unionBox} from '../../src/editor/boxes';

test('moves snap to the slide centre and to other objects, within tolerance only', () => {
  const near = {x: 758, y: 300, width: 400, height: 100};            // centre 958 ~ slide centre 960
  const snapped = snapMove(near, [], slide, 6);
  assert.equal(snapped.box.x, 760);
  assert.ok(snapped.guides.some(g => g.axis === 'x' && g.at === 960));
  const far = {...near, x: 700};
  assert.equal(snapMove(far, [], slide, 6).box.x, 700);
  const other = {x: 100, y: 600, width: 300, height: 80};
  const edge = snapMove({x: 104, y: 200, width: 200, height: 50}, [other], slide, 6);
  assert.equal(edge.box.x, 100);                                     // left edges align
  assert.ok(edge.guides.some(g => g.axis === 'x' && g.at === 100 && g.from <= 200 && g.to >= 680));
});

test('moves snap to equal spacing between neighbours and report the spacing', () => {
  const left = {x: 100, y: 400, width: 200, height: 100}, right = {x: 900, y: 400, width: 200, height: 100};
  const middle = {x: 497, y: 410, width: 200, height: 80};           // equal gaps at x=500
  const snapped = snapMove(middle, [left, right], {x: 0, y: 0, width: 5000, height: 5000}, 6);
  assert.equal(snapped.box.x, 500);
  assert.equal(snapped.spacing.filter(s => s.axis === 'x').length, 2);
});

test('resizes snap the dragged edge to lines and to matching sizes', () => {
  const other = {x: 1000, y: 700, width: 320, height: 90};
  const box = {x: 100, y: 100, width: 316, height: 50};
  assert.equal(snapResize(box, 'e', [other], slide, 6).box.width, 320);   // same width as other
  const toEdge = snapResize({...box, width: 896}, 'e', [other], slide, 6);
  assert.equal(toEdge.box.x + toEdge.box.width, 1000);                   // right edge meets other's left
  const west = snapResize({x: 997, y: 100, width: 100, height: 50}, 'w', [other], slide, 6);
  assert.equal(west.box.x, 1000); assert.equal(west.box.x + west.box.width, 1097);
});

test('align uses the selection union, or the slide for one object', () => {
  const boxes = [{x: 100, y: 100, width: 100, height: 50}, {x: 300, y: 250, width: 200, height: 100}];
  assert.deepEqual(alignBoxes(boxes, 'left', slide).map(b => b.x), [100, 100]);
  assert.deepEqual(alignBoxes(boxes, 'right', slide).map(b => b.x + b.width), [500, 500]);
  assert.deepEqual(alignBoxes(boxes, 'middle', slide).map(b => b.y + b.height / 2), [225, 225]);
  assert.deepEqual(alignBoxes([boxes[0]], 'center', slide)[0].x, 910);
});

test('distribution equalizes gaps and keeps the outermost objects fixed', () => {
  const boxes = [{x: 0, y: 0, width: 100, height: 10}, {x: 900, y: 0, width: 100, height: 10}, {x: 130, y: 0, width: 200, height: 10}];
  const out = distributeBoxes(boxes, 'x');
  assert.equal(out[0].x, 0); assert.equal(out[1].x, 900);
  assert.equal(out[2].x, 400);                                        // 0 + 100 + gap (1000-400)/2
});

test('group resize maps every member through the union', () => {
  const boxes = [{x: 100, y: 100, width: 100, height: 100}, {x: 300, y: 200, width: 100, height: 100}];
  const from = unionBox(boxes), to = {x: 100, y: 100, width: 600, height: 400};
  const out = scaleGroup(boxes, from, to);
  assert.deepEqual(out[1], {x: 500, y: 300, width: 200, height: 200});
  assert.deepEqual(unionBox(out), to);
});

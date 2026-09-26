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

/** Pure box geometry for direct manipulation, in canonical slide pixels.
 *
 * Every movable object is measured into the same absolute 1920x1080 frame,
 * so moving, resizing and nudging share one implementation regardless of
 * how each object persists its position.
 */
export interface Box { x: number; y: number; width: number; height: number }
/** Compass handle: which edges a resize drags. */
export type Handle = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw';
export const HANDLES: readonly Handle[] = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];
export interface Limits { bounds: Box; minWidth: number; minHeight: number }

const round = (value: number) => Math.round(value * 10) / 10;
export function roundBox(box: Box): Box {
  return {x: round(box.x), y: round(box.y), width: round(box.width), height: round(box.height)};
}

/** Translate without leaving the slide; an oversized box pins to the origin. */
export function moveBox(box: Box, dx: number, dy: number, bounds: Box): Box {
  const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(Math.max(min, max), value));
  return {...box,
    x: clamp(box.x + dx, bounds.x, bounds.x + bounds.width - box.width),
    y: clamp(box.y + dy, bounds.y, bounds.y + bounds.height - box.height)};
}

/** Drag the edges a handle names. The opposite edge (or the centre for
 * proportional corner resizes) stays fixed; size and slide limits hold. */
export function resizeBox(box: Box, handle: Handle, dx: number, dy: number,
  {bounds, minWidth, minHeight}: Limits, keepAspect = false): Box {
  const west = handle.includes('w'), east = handle.includes('e');
  const north = handle.includes('n'), south = handle.includes('s');
  let left = box.x, right = box.x + box.width, top = box.y, bottom = box.y + box.height;
  if (west) left = Math.min(right - minWidth, Math.max(bounds.x, left + dx));
  if (east) right = Math.max(left + minWidth, Math.min(bounds.x + bounds.width, right + dx));
  if (north) top = Math.min(bottom - minHeight, Math.max(bounds.y, top + dy));
  if (south) bottom = Math.max(top + minHeight, Math.min(bounds.y + bounds.height, bottom + dy));
  let next = {x: left, y: top, width: right - left, height: bottom - top};
  if (keepAspect && box.width > 0 && box.height > 0) next = proportional(box, next, handle, {bounds, minWidth, minHeight});
  return next;
}

function proportional(original: Box, next: Box, handle: Handle, {bounds, minWidth, minHeight}: Limits): Box {
  const ratio = original.width / original.height;
  const horizontal = handle.includes('e') || handle.includes('w');
  const vertical = handle.includes('n') || handle.includes('s');
  // Corners follow the axis the pointer moved more (growing or shrinking);
  // edges drive their own axis.
  const sx = next.width / original.width, sy = next.height / original.height;
  let scale = horizontal && vertical ? (Math.abs(Math.log(sx)) >= Math.abs(Math.log(sy)) ? sx : sy)
    : horizontal ? sx : sy;
  scale = Math.max(scale, minWidth / original.width, minHeight / original.height);
  // The anchor is the fixed opposite edge; an edge handle keeps the other
  // axis centred so the box grows symmetrically about its midline.
  const anchorX = handle.includes('w') ? original.x + original.width
    : handle.includes('e') ? original.x : original.x + original.width / 2;
  const anchorY = handle.includes('n') ? original.y + original.height
    : handle.includes('s') ? original.y : original.y + original.height / 2;
  const fx = handle.includes('w') ? 1 : handle.includes('e') ? 0 : .5;
  const fy = handle.includes('n') ? 1 : handle.includes('s') ? 0 : .5;
  // Largest scale that keeps every edge on the slide from this anchor.
  const room = (anchor: number, fraction: number, min: number, max: number, extent: number) => {
    const limits = [];
    if (fraction > 0) limits.push((anchor - min) / (fraction * extent));
    if (fraction < 1) limits.push((max - anchor) / ((1 - fraction) * extent));
    return Math.min(...limits);
  };
  scale = Math.min(scale,
    room(anchorX, fx, bounds.x, bounds.x + bounds.width, original.width),
    room(anchorY, fy, bounds.y, bounds.y + bounds.height, original.height));
  const width = original.width * scale, height = width / ratio;
  return {x: anchorX - fx * width, y: anchorY - fy * height, width, height};
}

/** Arrow-key movement: 1 px, or 10 px with Shift, never off the slide. */
export function nudgeBox(box: Box, key: string, large: boolean, bounds: Box): Box | null {
  const step = large ? 10 : 1;
  const delta: Record<string, [number, number]> = {
    ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step]};
  return delta[key] ? moveBox(box, delta[key][0], delta[key][1], bounds) : null;
}

/** A pointer travelling less than this is a click, not a drag (screen px). */
export const DRAG_THRESHOLD = 4;
export function isDrag(dx: number, dy: number): boolean {
  return Math.hypot(dx, dy) >= DRAG_THRESHOLD;
}

// ---------------------------------------------------------------------------
// Snapping. Candidates are the slide's edges and centre lines and every other
// object's edges and centres; a move may also snap to equal spacing between
// its neighbours, and a resize to another object's width or height. Adapted
// from Deckwerk's snapping model (MIT), reduced to what this editor draws.

/** A guide line: alignment at `at` on `axis`, drawn from `from` to `to` across it. */
export interface Guide { axis: 'x' | 'y'; at: number; from: number; to: number }
/** An equal-spacing bar: the empty span `start..end` on `axis`, drawn at `cross`. */
export interface Spacing { axis: 'x' | 'y'; start: number; end: number; cross: number }
export interface Snapped { box: Box; guides: Guide[]; spacing: Spacing[] }

type Axis = 'x' | 'y';
const START = {x: 'x', y: 'y'} as const, SIZE = {x: 'width', y: 'height'} as const;
const other = (axis: Axis): Axis => axis === 'x' ? 'y' : 'x';
const lines = (box: Box, axis: Axis) =>
  [box[START[axis]], box[START[axis]] + box[SIZE[axis]] / 2, box[START[axis]] + box[SIZE[axis]]];
const overlaps = (a: Box, b: Box, axis: Axis) =>
  a[START[axis]] < b[START[axis]] + b[SIZE[axis]] && b[START[axis]] < a[START[axis]] + a[SIZE[axis]];

/** Best translation along one axis within `tolerance`, or null. */
function moveOffset(box: Box, others: Box[], slide: Box, axis: Axis, tolerance: number): number | null {
  let best: number | null = null;
  const consider = (delta: number) => {
    if (Math.abs(delta) <= tolerance && (best === null || Math.abs(delta) < Math.abs(best))) best = delta;
  };
  const moving = lines(box, axis);
  for (const target of [slide, ...others]) for (const line of lines(target, axis))
    for (const edge of moving) consider(line - edge);
  // Equal spacing: between the nearest neighbours on each side, or matching a
  // gap that already exists between other objects in the same row/column.
  const cross = other(axis), start = START[axis], size = SIZE[axis];
  const row = others.filter(item => overlaps(item, box, cross));
  const before = row.filter(item => item[start] + item[size] <= box[start] + tolerance)
    .sort((a, b) => (b[start] + b[size]) - (a[start] + a[size]))[0];
  const after = row.filter(item => item[start] >= box[start] + box[size] - tolerance)
    .sort((a, b) => a[start] - b[start])[0];
  if (before && after) consider((before[start] + before[size] + after[start] - box[size]) / 2 - box[start]);
  const sorted = [...row].sort((a, b) => a[start] - b[start]);
  const gaps = sorted.slice(1).map((item, index) => item[start] - (sorted[index][start] + sorted[index][size])).filter(gap => gap > 0);
  for (const gap of gaps) {
    if (before) consider(before[start] + before[size] + gap - box[start]);
    if (after) consider(after[start] - gap - box[size] - box[start]);
  }
  return best;
}

/** Guides and spacing bars that hold exactly for a settled box. */
export function describeSnap(box: Box, others: Box[], slide: Box): {guides: Guide[]; spacing: Spacing[]} {
  const guides: Guide[] = [], spacing: Spacing[] = [];
  for (const axis of ['x', 'y'] as Axis[]) {
    const cross = other(axis);
    for (const edge of lines(box, axis)) {
      const hits = [slide, ...others].filter(target => lines(target, axis).some(line => Math.abs(line - edge) < .5));
      if (!hits.length) continue;
      const span = [box, ...hits.filter(hit => hit !== slide)];
      const from = Math.min(...span.map(b => b[START[cross]])), to = Math.max(...span.map(b => b[START[cross]] + b[SIZE[cross]]));
      guides.push({axis, at: edge, from: hits.includes(slide) && span.length === 1 ? slide[START[cross]] : from,
        to: hits.includes(slide) && span.length === 1 ? slide[START[cross]] + slide[SIZE[cross]] : to});
    }
    const start = START[axis], size = SIZE[axis];
    const row = others.filter(item => overlaps(item, box, cross));
    const before = row.filter(item => item[start] + item[size] <= box[start] + .5)
      .sort((a, b) => (b[start] + b[size]) - (a[start] + a[size]))[0];
    const after = row.filter(item => item[start] >= box[start] + box[size] - .5).sort((a, b) => a[start] - b[start])[0];
    if (before && after) {
      const left = box[start] - (before[start] + before[size]), right = after[start] - (box[start] + box[size]);
      if (left > 0 && Math.abs(left - right) < .5) {
        const mid = box[START[cross]] + box[SIZE[cross]] / 2;
        spacing.push({axis, start: before[start] + before[size], end: box[start], cross: mid},
          {axis, start: box[start] + box[size], end: after[start], cross: mid});
      }
    }
  }
  return {guides, spacing};
}

export function snapMove(box: Box, others: Box[], slide: Box, tolerance: number): Snapped {
  const dx = moveOffset(box, others, slide, 'x', tolerance) ?? 0;
  const dy = moveOffset(box, others, slide, 'y', tolerance) ?? 0;
  const snapped = moveBox(box, dx, dy, slide);
  return {box: snapped, ...describeSnap(snapped, others, slide)};
}

/** Snap only the edges a handle drags, to lines or to another object's size. */
export function snapResize(box: Box, handle: Handle, others: Box[], slide: Box, tolerance: number): Snapped {
  let {x, y, width, height} = box;
  const pick = (candidates: number[], value: number) => {
    let best: number | null = null;
    for (const candidate of candidates)
      if (Math.abs(candidate - value) <= tolerance && (best === null || Math.abs(candidate - value) < Math.abs(best - value))) best = candidate;
    return best;
  };
  const xs = [slide, ...others].flatMap(b => lines(b, 'x')), ys = [slide, ...others].flatMap(b => lines(b, 'y'));
  if (handle.includes('e')) {
    const edge = pick([...xs, ...others.map(b => x + b.width)], x + width);
    if (edge !== null) width = edge - x;
  } else if (handle.includes('w')) {
    const right = x + width, edge = pick([...xs, ...others.map(b => right - b.width)], x);
    if (edge !== null) { x = edge; width = right - edge; }
  }
  if (handle.includes('s')) {
    const edge = pick([...ys, ...others.map(b => y + b.height)], y + height);
    if (edge !== null) height = edge - y;
  } else if (handle.includes('n')) {
    const bottom = y + height, edge = pick([...ys, ...others.map(b => bottom - b.height)], y);
    if (edge !== null) { y = edge; height = bottom - edge; }
  }
  const snapped = width > 0 && height > 0 ? {x, y, width, height} : box;
  return {box: snapped, ...describeSnap(snapped, others, slide)};
}

// ---------------------------------------------------------------------------
// Several objects. Alignment references the selection's union, or the slide
// for a single object; distribution keeps the outermost objects fixed.

export type Alignment = 'left' | 'center' | 'right' | 'top' | 'middle' | 'bottom';
export function unionBox(boxes: Box[]): Box {
  const x = Math.min(...boxes.map(b => b.x)), y = Math.min(...boxes.map(b => b.y));
  return {x, y, width: Math.max(...boxes.map(b => b.x + b.width)) - x, height: Math.max(...boxes.map(b => b.y + b.height)) - y};
}
export function alignBoxes(boxes: Box[], mode: Alignment, slide: Box): Box[] {
  const reference = boxes.length > 1 ? unionBox(boxes) : slide;
  return boxes.map(box => {
    switch (mode) {
      case 'left': return {...box, x: reference.x};
      case 'center': return {...box, x: reference.x + (reference.width - box.width) / 2};
      case 'right': return {...box, x: reference.x + reference.width - box.width};
      case 'top': return {...box, y: reference.y};
      case 'middle': return {...box, y: reference.y + (reference.height - box.height) / 2};
      case 'bottom': return {...box, y: reference.y + reference.height - box.height};
    }
  });
}
/** Equal gaps between objects ordered along an axis; the first and last stay put. */
export function distributeBoxes(boxes: Box[], axis: Axis): Box[] {
  if (boxes.length < 3) return boxes.map(box => ({...box}));
  const start = START[axis], size = SIZE[axis];
  const order = boxes.map((box, index) => ({box, index})).sort((a, b) => a.box[start] - b.box[start]);
  const first = order[0].box, last = order[order.length - 1].box;
  const occupied = order.reduce((sum, item) => sum + item.box[size], 0);
  const gap = (last[start] + last[size] - first[start] - occupied) / (order.length - 1);
  const result = boxes.map(box => ({...box}));
  let cursor = first[start];
  for (const item of order) { result[item.index][start] = cursor; cursor += item.box[size] + gap; }
  return result;
}
/** Map each member from the group's old union to its new union. */
export function scaleGroup(boxes: Box[], from: Box, to: Box): Box[] {
  const sx = from.width ? to.width / from.width : 1, sy = from.height ? to.height / from.height : 1;
  return boxes.map(box => ({x: to.x + (box.x - from.x) * sx, y: to.y + (box.y - from.y) * sy,
    width: box.width * sx, height: box.height * sy}));
}

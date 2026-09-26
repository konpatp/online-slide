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

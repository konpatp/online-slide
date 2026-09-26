/** One selection and move/resize layer for every box-shaped slide object.
 *
 * Objects persist their geometry differently (text regions offset from their
 * flow position, visual objects as fractions of their article, diagram nodes
 * in paper coordinates). Each registers an adapter that converts one absolute
 * canonical box into its own storage; the layer owns every gesture, the frame,
 * the handles, keyboard nudging and change boundaries. Lines and vectors are
 * not boxes and keep their endpoint controls.
 */
import {CANONICAL_SLIDE_WIDTH, CANONICAL_SLIDE_HEIGHT} from './viewport';
import {HANDLES, isDrag, moveBox, nudgeBox, resizeBox, roundBox} from './boxes';
import type {Box, Handle} from './boxes';

export interface BoxEdit { update(next: Box): void; finish?(): void }
export interface TransformTarget {
  /** Unique on the page, e.g. `slide@component`. */
  key: string;
  /** Accessible noun used in handle names: "Move text region". */
  label: string;
  /** Pointer surfaces; the first is also the measured box unless `bounds` says otherwise. */
  hits: HTMLElement[];
  canvas: HTMLElement;
  /** Undo group for this object, shared with any other writer of the same geometry. */
  group: string;
  bounds?(): Box;
  /** Where the box may go; defaults to the slide. */
  area?(): Box;
  resizable?: boolean;
  /** Images keep proportions unless Shift; everything else only with Shift. */
  keepAspect?: boolean;
  minWidth?: number; minHeight?: number;
  /** False: body drags do nothing; the frame's move grip still works. */
  bodyDrag?: boolean;
  /** Descendants that keep their own pointer gestures (chart legends, links). */
  nativeSelector?: string;
  /** Editable text under the pointer: a click edits it, a drag moves the object. */
  textAt?(node: Element): HTMLElement | null;
  select(): void;
  /** Start one geometry change; the layer brackets it with beginChange/persist. */
  edit(): BoxEdit;
}
interface LayerHost {
  isEditMode(): boolean;
  /** Move keyboard focus from any text to the object-selection surface. */
  focusObject(): void;
  beginChange(group: string): void;
  persist(): void;
}
interface Gesture {
  target: TransformTarget; kind: 'move' | Handle; pointerId: number;
  startX: number; startY: number; scale: number;
  text: HTMLElement | null; dragging: boolean;
  origin?: Box; area?: Box; edit?: BoxEdit;
}

const SLIDE: Box = {x: 0, y: 0, width: CANONICAL_SLIDE_WIDTH, height: CANONICAL_SLIDE_HEIGHT};
const IGNORED = 'button, input, select, textarea, a[href], [data-transform-control]';
const HANDLE_NAMES: Record<Handle, string> = {n: 'top', s: 'bottom', e: 'right', w: 'left',
  ne: 'top-right', nw: 'top-left', se: 'bottom-right', sw: 'bottom-left'};

/** Rendered-to-canonical factor of a proportionally scaled slide canvas. */
export function canvasScale(canvas: HTMLElement): number {
  const rect = canvas.getBoundingClientRect();
  return rect.width / CANONICAL_SLIDE_WIDTH || 1;
}
/** An element's painted box in canonical slide pixels. */
export function measureBox(element: Element, canvas: HTMLElement): Box {
  const outer = canvas.getBoundingClientRect(), rect = element.getBoundingClientRect();
  const scale = outer.width / CANONICAL_SLIDE_WIDTH || 1;
  return {x: (rect.left - outer.left) / scale, y: (rect.top - outer.top) / scale,
    width: rect.width / scale, height: rect.height / scale};
}

export function createTransformLayer(host: LayerHost) {
  const targets = new Map<string, TransformTarget>();
  const owners = new WeakMap<HTMLElement, TransformTarget>();
  const claimed = new WeakSet<Event>();
  let selectedKey: string | null = null;
  let frame: HTMLElement | null = null;
  let gesture: Gesture | null = null;
  let follow: ResizeObserver | null = null;
  // Whether the layer (or a native gesture it deferred to) owns the current
  // press; the click that ends it must not also mean "clicked empty slide".
  let ownsPress = false;
  document.addEventListener('pointerdown', () => { ownsPress = false; }, true);
  const claim = (event: Event) => { claimed.add(event); ownsPress = true; };

  const boundsOf = (target: TransformTarget) =>
    target.bounds ? target.bounds() : measureBox(target.hits[0], target.canvas);

  function register(target: TransformTarget) {
    targets.set(target.key, target);
    target.hits.forEach(element => {
      element.dataset.transformTarget = target.key;
      if (owners.has(element)) { owners.set(element, target); return; }
      owners.set(element, target);
      element.addEventListener('pointerdown', event => {
        const owner = owners.get(element);
        if (owner && targets.get(owner.key) === owner) pointerDown(owner, event, 'move', true);
      });
    });
    if (target.key === selectedKey) requestAnimationFrame(sync);
  }

  function pointerDown(target: TransformTarget, event: PointerEvent, kind: Gesture['kind'], body: boolean) {
    if (claimed.has(event) || !host.isEditMode() || event.button !== 0) return;
    const node = event.target as Element;
    if (body) {
      if (node.closest(IGNORED)) return;
      // Native gestures (chart zoom, legend drag) keep the pointer; the
      // object is still selected so its border and handles appear.
      if (target.nativeSelector && node.closest(target.nativeSelector)) { claim(event); select(target.key); return; }
      const text = target.textAt?.(node) || null;
      const active = document.activeElement;
      // Text being edited owns its pointer: drag selects words, not the box.
      if (text && active && (text === active || text.contains(active))) { claim(event); select(target.key); return; }
      if (target.bodyDrag === false) return;
      claim(event);
      event.preventDefault();
      select(target.key);
      start(target, event, kind, text);
      return;
    }
    claim(event);
    event.preventDefault(); event.stopPropagation();
    select(target.key);
    start(target, event, kind, null);
  }

  function start(target: TransformTarget, event: PointerEvent, kind: Gesture['kind'], text: HTMLElement | null) {
    finishGesture(false);
    // Object gestures address the object: keys now act on it, not on text.
    host.focusObject();
    gesture = {target, kind, pointerId: event.pointerId, startX: event.clientX, startY: event.clientY,
      scale: canvasScale(target.canvas), text, dragging: false};
    document.addEventListener('pointermove', pointerMove);
    document.addEventListener('pointerup', pointerUp);
    document.addEventListener('pointercancel', pointerCancel);
  }

  function pointerMove(event: PointerEvent) {
    if (!gesture || event.pointerId !== gesture.pointerId) return;
    const screenX = event.clientX - gesture.startX, screenY = event.clientY - gesture.startY;
    if (!gesture.dragging) {
      if (!isDrag(screenX, screenY)) return;
      gesture.dragging = true;
      gesture.origin = boundsOf(gesture.target);
      gesture.area = gesture.target.area?.() || SLIDE;
      host.beginChange(gesture.target.group);
      gesture.edit = gesture.target.edit();
      document.body.classList.add(gesture.kind === 'move' ? 'transform-moving' : 'transform-resizing');
    }
    event.preventDefault();
    const dx = screenX / gesture.scale, dy = screenY / gesture.scale;
    const {target, origin, area} = gesture as Required<Gesture>;
    const next = gesture.kind === 'move' ? moveBox(origin, dx, dy, area)
      : resizeBox(origin, gesture.kind, dx, dy,
        {bounds: area, minWidth: target.minWidth ?? 48, minHeight: target.minHeight ?? 28},
        Boolean(target.keepAspect) !== event.shiftKey);
    // Re-assert the change each step: if anything closed the undo step early,
    // the rest of the drag still lands in history rather than outside it.
    host.beginChange(target.group);
    gesture.edit!.update(roundBox(next));
    sync();
  }

  function pointerUp(event: PointerEvent) {
    if (!gesture || event.pointerId !== gesture.pointerId) return;
    const {dragging, text} = gesture;
    finishGesture(true);
    if (!dragging && text) editTextAt(text, event.clientX, event.clientY);
  }
  function pointerCancel(event: PointerEvent) {
    if (gesture && event.pointerId === gesture.pointerId) finishGesture(true);
  }
  function finishGesture(commit: boolean) {
    document.removeEventListener('pointermove', pointerMove);
    document.removeEventListener('pointerup', pointerUp);
    document.removeEventListener('pointercancel', pointerCancel);
    document.body.classList.remove('transform-moving', 'transform-resizing');
    const done = gesture; gesture = null;
    if (done?.dragging && done.edit) {
      swallowNextClick();
      done.edit.finish?.();
      if (commit) host.persist();
      sync();
    }
  }

  /** A drag that ends over another element produces a click on their common
   * ancestor (often the slide, which would deselect); it is not a click. */
  function swallowNextClick() {
    const swallow = (event: Event) => { event.stopPropagation(); event.preventDefault(); };
    window.addEventListener('click', swallow, {capture: true, once: true});
    setTimeout(() => window.removeEventListener('click', swallow, {capture: true}), 0);
  }

  /** A click on text edits it at the pointer, exactly like native editing. */
  function editTextAt(text: HTMLElement, x: number, y: number) {
    if (!text.isContentEditable) return;
    text.focus({preventScroll: true});
    const doc = document as Document & {caretPositionFromPoint?(x: number, y: number): {offsetNode: Node; offset: number} | null};
    let range: Range | null = null;
    if (doc.caretRangeFromPoint) range = doc.caretRangeFromPoint(x, y);
    else if (doc.caretPositionFromPoint) {
      const position = doc.caretPositionFromPoint(x, y);
      if (position) { range = document.createRange(); range.setStart(position.offsetNode, position.offset); }
    }
    const selection = getSelection();
    if (!selection) return;
    if (!range || !text.contains(range.startContainer)) {
      range = document.createRange(); range.selectNodeContents(text); range.collapse(false);
    }
    range.collapse(true);
    selection.removeAllRanges(); selection.addRange(range);
  }

  /** Selection may name an object that registers a frame later (renderers
   * register after layout); the frame appears as soon as it does. */
  function select(key: string | null) {
    const changed = selectedKey !== key;
    selectedKey = key;
    const target = key ? targets.get(key) : null;
    if (target && changed) target.select();
    sync();
  }

  function removeFrame() {
    follow?.disconnect(); follow = null;
    frame?.remove(); frame = null;
  }

  function buildFrame(target: TransformTarget) {
    removeFrame();
    const element = document.createElement('div');
    element.className = 'transform-frame';
    element.dataset.transformFrame = target.key;
    element.dataset.transformControl = '';
    const grip = control('transform-move-grip', 'Move ' + target.label, 'Drag to move');
    grip.addEventListener('pointerdown', event => pointerDown(target, event, 'move', false));
    element.appendChild(grip);
    // The border is a move surface, so text being edited and charts that
    // keep their own drags can still be moved directly.
    ['top', 'right', 'bottom', 'left'].forEach(side => {
      const edge = document.createElement('div');
      edge.className = 'transform-edge transform-edge-' + side;
      edge.dataset.transformControl = '';
      edge.addEventListener('pointerdown', event => pointerDown(target, event, 'move', false));
      element.appendChild(edge);
    });
    if (target.resizable !== false) HANDLES.forEach(handle => {
      // The bottom-right corner keeps the historical accessible name.
      const name = handle === 'se' ? 'Resize ' + target.label
        : 'Resize ' + target.label + ' from ' + HANDLE_NAMES[handle];
      const button = control('transform-handle transform-handle-' + handle, name,
        'Drag to resize; Shift keeps proportions');
      button.dataset.handle = handle;
      button.addEventListener('pointerdown', event => pointerDown(target, event, handle, false));
      element.appendChild(button);
    });
    element.addEventListener('click', event => event.stopPropagation());
    // Outside the clipped slide, so handles on objects at the edge stay reachable.
    frameHost(target).appendChild(element);
    frame = element;
    if (window.ResizeObserver) {
      follow = new ResizeObserver(() => requestAnimationFrame(sync));
      target.hits.forEach(node => follow!.observe(node));
    }
  }
  function control(className: string, label: string, title: string) {
    const button = document.createElement('button');
    button.type = 'button'; button.className = className; button.tabIndex = -1;
    button.setAttribute('aria-label', label); button.title = title;
    button.dataset.transformControl = '';
    return button;
  }

  /** Keep the frame on the selected object after any change of layout. */
  function sync() {
    const target = selectedKey ? targets.get(selectedKey) : null;
    if (!target || !host.isEditMode() || !target.hits[0].isConnected || !target.canvas.isConnected) {
      removeFrame(); return;
    }
    const parent = frameHost(target);
    if (!frame || frame.dataset.transformFrame !== target.key || frame.parentElement !== parent) buildFrame(target);
    const box = boundsOf(target), scale = canvasScale(target.canvas);
    const slide = target.canvas.getBoundingClientRect(), outer = parent.getBoundingClientRect();
    Object.assign(frame!.style, {left: (slide.left - outer.left + box.x * scale) + 'px',
      top: (slide.top - outer.top + box.y * scale) + 'px',
      width: box.width * scale + 'px', height: box.height * scale + 'px'});
  }
  const frameHost = (target: TransformTarget) => target.canvas.parentElement || target.canvas;

  /** Arrow keys move the selected object; returns whether the key was used. */
  function nudge(event: KeyboardEvent): boolean {
    const target = selectedKey ? targets.get(selectedKey) : null;
    if (!target || !host.isEditMode() || event.metaKey || event.ctrlKey || event.altKey) return false;
    const origin = boundsOf(target);
    const next = nudgeBox(origin, event.key, event.shiftKey, target.area?.() || SLIDE);
    if (!next) return false;
    host.beginChange(target.group + ':nudge');
    const edit = target.edit();
    edit.update(roundBox(next)); edit.finish?.();
    host.persist();
    sync();
    return true;
  }

  function clear() {
    finishGesture(false);
    targets.clear();
    removeFrame();
  }

  /** Start a move from an external grip (e.g. a layout frame's label). */
  function grab(key: string, event: PointerEvent) {
    const target = targets.get(key);
    if (target) pointerDown(target, event, 'move', false);
  }

  return {register, select, sync, nudge, clear, grab,
    /** True while the press that produced the current click belonged to an object. */
    ownsPress: () => ownsPress,
    selected: () => selectedKey,
    has: (key: string) => targets.has(key),
    unregister(key: string) { targets.delete(key); if (selectedKey === key) select(null); }};
}
export type TransformLayer = ReturnType<typeof createTransformLayer>;

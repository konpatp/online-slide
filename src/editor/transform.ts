/** One selection and move/resize layer for every box-shaped slide object.
 *
 * Objects persist their geometry differently (text regions offset from their
 * flow position, visual objects as fractions of their article, diagram nodes
 * in paper coordinates). Each registers an adapter that converts one absolute
 * canonical box into its own storage; the layer owns selection (one object or
 * several), every gesture, the frame and handles, snapping guides, keyboard
 * nudging, alignment and change boundaries. Lines and vectors are not boxes
 * and keep their endpoint controls.
 */
import {CANONICAL_SLIDE_WIDTH, CANONICAL_SLIDE_HEIGHT} from './viewport';
import {HANDLES, alignBoxes, distributeBoxes, isDrag, moveBox, nudgeBox, resizeBox, roundBox,
  scaleGroup, snapMove, snapResize, unionBox} from './boxes';
import type {Alignment, Box, Guide, Handle, Spacing} from './boxes';

export interface BoxEdit { update(next: Box): void; finish?(): void }
/** Which saved object a target is, for whole-object commands such as delete. */
export type TargetIdentity = {slideId: string; componentId: string} | {slideId: string; objectId: string; objectKind: string};
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
  identity?: TargetIdentity;
  bounds?(): Box;
  /** Where the box may go; defaults to the slide. */
  area?(): Box;
  resizable?: boolean;
  /** Images keep proportions unless Shift; everything else only with Shift. */
  keepAspect?: boolean;
  minWidth?: number; minHeight?: number;
  /** False: body drags and box selection skip it; its explicit grip still works. */
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
  /** The selection changed (count or members); tools may enable or disable. */
  selectionChanged?(keys: string[]): void;
}
interface Gesture {
  kind: 'move' | Handle; pointerId: number; startX: number; startY: number; scale: number;
  canvas: HTMLElement; members: TransformTarget[]; text: HTMLElement | null;
  /** A plain click on one member of a multi-selection selects just that member. */
  collapseTo: string | null;
  dragging: boolean;
  origins?: Box[]; union?: Box; areas?: Box[]; edits?: BoxEdit[]; others?: Box[];
}

const SLIDE: Box = {x: 0, y: 0, width: CANONICAL_SLIDE_WIDTH, height: CANONICAL_SLIDE_HEIGHT};
const IGNORED = 'button, input, select, textarea, a[href], [data-transform-control]';
const HANDLE_NAMES: Record<Handle, string> = {n: 'top', s: 'bottom', e: 'right', w: 'left',
  ne: 'top-right', nw: 'top-left', se: 'bottom-right', sw: 'bottom-left'};
/** Snapping tolerance in screen pixels; Alt (Option) disables snapping. */
const SNAP_SCREEN_PX = 6;

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
const inside = (box: Box, area: Box) => moveBox(box, 0, 0, area);

export function createTransformLayer(host: LayerHost) {
  const targets = new Map<string, TransformTarget>();
  const owners = new WeakMap<HTMLElement, TransformTarget>();
  const claimed = new WeakSet<Event>();
  /** Ordered selection; the last key is the primary object tools act on. */
  let selection: string[] = [];
  let frame: HTMLElement | null = null;
  let overlay: HTMLElement | null = null;
  let gesture: Gesture | null = null;
  let follow: ResizeObserver | null = null;
  let notifying = false, settling = false;
  // Whether the layer (or a native gesture it deferred to) owns the current
  // press; the click that ends it must not also mean "clicked empty slide".
  let ownsPress = false;
  document.addEventListener('pointerdown', () => { ownsPress = false; }, true);
  const claim = (event: Event) => { claimed.add(event); ownsPress = true; };

  const boundsOf = (target: TransformTarget) =>
    target.bounds ? target.bounds() : measureBox(target.hits[0], target.canvas);
  const live = (target: TransformTarget | undefined): target is TransformTarget =>
    Boolean(target && target.hits[0].isConnected && target.canvas.isConnected);
  const members = () => selection.map(key => targets.get(key)).filter(live);
  const groupOf = (list: TransformTarget[]) => list.length === 1 ? list[0].group : 'selection:' + list.map(t => t.key).join(',');

  function register(target: TransformTarget) {
    targets.set(target.key, target);
    target.hits.forEach(element => {
      element.dataset.transformTarget = target.key;
      if (owners.has(element)) { owners.set(element, target); return; }
      owners.set(element, target);
      element.addEventListener('pointerdown', event => {
        const owner = owners.get(element);
        if (owner && targets.get(owner.key) === owner) pointerDown(owner, event);
      });
    });
    if (selection.includes(target.key)) requestAnimationFrame(sync);
  }

  // --- selection ------------------------------------------------------------
  function setSelection(keys: string[]) {
    const previous = selection;
    selection = keys.filter((key, index) => keys.indexOf(key) === index);
    const primary = selection.length ? targets.get(selection[selection.length - 1]) : undefined;
    if (primary && previous[previous.length - 1] !== primary.key) {
      notifying = true;
      try { primary.select(); } finally { notifying = false; }
    }
    if (previous.join() !== selection.join()) host.selectionChanged?.(selection.slice());
    sync();
  }
  /** Select one object (or none) on the editor's behalf. Naming an object
   * that is already selected keeps the group: the editor's own click handlers
   * follow every layer gesture, and only the layer decides when a plain click
   * collapses a group (see pointerUp). */
  function select(key: string | null) {
    if (notifying || settling || (key && selection.includes(key))) return;
    setSelection(key ? [key] : []);
  }
  function toggle(key: string) {
    setSelection(selection.includes(key) ? selection.filter(item => item !== key) : [...selection, key]);
  }
  /** Every movable object on the slide showing `canvas` (Ctrl/Cmd+A). */
  function selectAll(canvas: HTMLElement) {
    setSelection([...targets.values()].filter(t => live(t) && t.canvas === canvas && t.bodyDrag !== false).map(t => t.key));
  }

  // --- pointer gestures -----------------------------------------------------
  function pointerDown(target: TransformTarget, event: PointerEvent, handle?: 'move' | Handle) {
    if (claimed.has(event) || !host.isEditMode() || event.button !== 0) return;
    const node = event.target as Element;
    if (!handle) {
      if (node.closest(IGNORED)) return;
      // Native gestures (chart zoom, legend drag) keep the pointer; the
      // object is still selected so its border and handles appear.
      if (target.nativeSelector && node.closest(target.nativeSelector)) {
        claim(event); if (event.shiftKey) toggle(target.key); else if (!selection.includes(target.key)) select(target.key);
        settle();
        return;
      }
      const text = target.textAt?.(node) || null;
      const active = document.activeElement;
      // Text being edited owns its pointer: drag selects words, not the box.
      if (text && active && (text === active || text.contains(active))) { claim(event); select(target.key); return; }
      if (target.bodyDrag === false) return;
      claim(event); event.preventDefault();
      if (event.shiftKey) {
        // Shift adds or removes; dragging then moves whatever remains selected.
        toggle(target.key);
        if (selection.includes(target.key)) start(event, 'move', null, null);
        else settle();
        return;
      }
      const inGroup = selection.length > 1 && selection.includes(target.key);
      if (!inGroup) select(target.key);
      start(event, 'move', text, inGroup ? target.key : null);
      return;
    }
    // Frame controls act on the whole selection.
    claim(event); event.preventDefault(); event.stopPropagation();
    if (!selection.includes(target.key)) select(target.key);
    start(event, handle, null, null);
  }

  function start(event: PointerEvent, kind: Gesture['kind'], text: HTMLElement | null, collapseTo: string | null) {
    finishGesture(false);
    const list = members();
    if (!list.length) return;
    // Object gestures address the object: keys now act on it, not on text.
    host.focusObject();
    gesture = {kind, pointerId: event.pointerId, startX: event.clientX, startY: event.clientY,
      scale: canvasScale(list[0].canvas), canvas: list[0].canvas, members: list, text, collapseTo, dragging: false};
    document.addEventListener('pointermove', pointerMove);
    document.addEventListener('pointerup', pointerUp);
    document.addEventListener('pointercancel', pointerCancel);
  }

  function beginDrag(active: Gesture) {
    active.dragging = true;
    active.origins = active.members.map(boundsOf);
    active.union = unionBox(active.origins);
    active.areas = active.members.map(t => t.area?.() || SLIDE);
    const chosen = new Set(active.members);
    // Snap candidates: every other object on this slide, measured once.
    active.others = [...targets.values()].filter(t => live(t) && t.canvas === active.canvas && !chosen.has(t) && t.bodyDrag !== false)
      .map(boundsOf);
    host.beginChange(groupOf(active.members));
    active.edits = active.members.map(t => t.edit());
    document.body.classList.add(active.kind === 'move' ? 'transform-moving' : 'transform-resizing');
  }

  function pointerMove(event: PointerEvent) {
    if (!gesture || event.pointerId !== gesture.pointerId) return;
    const screenX = event.clientX - gesture.startX, screenY = event.clientY - gesture.startY;
    if (!gesture.dragging) {
      if (!isDrag(screenX, screenY)) return;
      beginDrag(gesture);
    }
    event.preventDefault();
    const active = gesture as Required<Gesture>;
    const dx = screenX / active.scale, dy = screenY / active.scale, single = active.members.length === 1;
    const area = single ? active.areas[0] : SLIDE;
    const tolerance = SNAP_SCREEN_PX / active.scale, snapping = !event.altKey;
    let union: Box, guides: Guide[] = [], spacing: Spacing[] = [];
    if (active.kind === 'move') {
      union = moveBox(active.union, dx, dy, area);
      if (snapping) ({box: union, guides, spacing} = snapMove(union, active.others, SLIDE, tolerance));
      union = inside(union, area);
    } else {
      const lead = active.members[0], keepAspect = Boolean(single && lead.keepAspect) !== event.shiftKey;
      union = resizeBox(active.union, active.kind, dx, dy,
        {bounds: area, minWidth: single ? lead.minWidth ?? 48 : 20, minHeight: single ? lead.minHeight ?? 28 : 12}, keepAspect);
      if (snapping && !keepAspect) ({box: union, guides, spacing} = snapResize(union, active.kind, active.others, SLIDE, tolerance));
      union = inside(union, area);
    }
    const boxes = active.kind === 'move'
      ? active.origins.map(box => ({...box, x: box.x + union.x - active.union.x, y: box.y + union.y - active.union.y}))
      : scaleGroup(active.origins, active.union, union);
    // Re-assert the change each step: if anything closed the undo step early,
    // the rest of the drag still lands in history rather than outside it.
    host.beginChange(groupOf(active.members));
    boxes.forEach((box, index) => active.edits[index].update(roundBox(inside(box, active.areas[index]))));
    drawGuides(active.canvas, guides, spacing);
    sync();
  }

  function pointerUp(event: PointerEvent) {
    if (!gesture || event.pointerId !== gesture.pointerId) return;
    const {dragging, text, collapseTo} = gesture;
    finishGesture(true);
    if (dragging) return;
    if (collapseTo) setSelection([collapseTo]);
    settle();
    if (text) editTextAt(text, event.clientX, event.clientY);
  }
  /** The click that ends a press the layer owned must not override the
   * layer's selection; afterwards the editor learns the primary object. */
  function settle() {
    settling = true;
    // The click is its own task after pointerup; release the hold once it has
    // been fully dispatched (or shortly after, if no click follows).
    let fallback = 0;
    const release = () => {
      window.removeEventListener('click', onClick, true); clearTimeout(fallback);
      if (!settling) return;
      settling = false;
      const primary = targets.get(selection[selection.length - 1]);
      if (live(primary)) { notifying = true; try { primary.select(); } finally { notifying = false; } }
      sync();
    };
    const onClick = () => setTimeout(release, 0);
    window.addEventListener('click', onClick, {capture: true, once: true});
    fallback = window.setTimeout(release, 350);
  }
  function pointerCancel(event: PointerEvent) {
    if (gesture && event.pointerId === gesture.pointerId) finishGesture(true);
  }
  function finishGesture(commit: boolean) {
    document.removeEventListener('pointermove', pointerMove);
    document.removeEventListener('pointerup', pointerUp);
    document.removeEventListener('pointercancel', pointerCancel);
    document.body.classList.remove('transform-moving', 'transform-resizing');
    drawGuides(null, [], []);
    const done = gesture; gesture = null;
    if (done?.dragging && done.edits) {
      swallowNextClick();
      done.edits.forEach(edit => edit.finish?.());
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
    const selectionRange = getSelection();
    if (!selectionRange) return;
    if (!range || !text.contains(range.startContainer)) {
      range = document.createRange(); range.selectNodeContents(text); range.collapse(false);
    }
    range.collapse(true);
    selectionRange.removeAllRanges(); selectionRange.addRange(range);
  }

  /** Drag on empty slide space: select every object the box fully encloses
   * (Shift adds to the selection). Called by the editor for unclaimed presses. */
  function marquee(canvas: HTMLElement, event: PointerEvent) {
    if (claimed.has(event) || !host.isEditMode() || event.button !== 0) return;
    // A plain click on empty space still deselects; only a drag owns the press.
    const startX = event.clientX, startY = event.clientY, additive = event.shiftKey, base = additive ? selection.slice() : [];
    const scale = canvasScale(canvas), outer = canvas.getBoundingClientRect();
    const toSlide = (x: number, y: number) => ({x: (x - outer.left) / scale, y: (y - outer.top) / scale});
    let band: HTMLElement | null = null, dragging = false;
    const move = (next: PointerEvent) => {
      if (next.pointerId !== event.pointerId) return;
      if (!dragging && !isDrag(next.clientX - startX, next.clientY - startY)) return;
      if (!dragging) {
        dragging = true; ownsPress = true; host.focusObject();
        band = document.createElement('div'); band.className = 'transform-marquee'; band.dataset.transformControl = '';
        frameHost(canvas).appendChild(band);
      }
      next.preventDefault();
      const a = toSlide(startX, startY), b = toSlide(next.clientX, next.clientY);
      const box = {x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), width: Math.abs(a.x - b.x), height: Math.abs(a.y - b.y)};
      place(band!, canvas, box);
      const enclosed = [...targets.values()].filter(t => live(t) && t.canvas === canvas && t.bodyDrag !== false)
        .filter(t => { const r = boundsOf(t); return r.x >= box.x && r.y >= box.y && r.x + r.width <= box.x + box.width && r.y + r.height <= box.y + box.height; })
        .map(t => t.key);
      setSelection([...base, ...enclosed]);
    };
    const end = (next: PointerEvent) => {
      if (next.pointerId !== event.pointerId) return;
      document.removeEventListener('pointermove', move);
      document.removeEventListener('pointerup', end);
      document.removeEventListener('pointercancel', end);
      band?.remove();
      if (dragging) swallowNextClick();
    };
    document.addEventListener('pointermove', move);
    document.addEventListener('pointerup', end);
    document.addEventListener('pointercancel', end);
  }

  // --- drawing --------------------------------------------------------------
  const frameHost = (canvas: HTMLElement) => canvas.parentElement || canvas;
  /** Position an element over a canonical box, in the host's screen pixels. */
  function place(element: HTMLElement, canvas: HTMLElement, box: Box) {
    const scale = canvasScale(canvas), slide = canvas.getBoundingClientRect(), outer = frameHost(canvas).getBoundingClientRect();
    Object.assign(element.style, {left: (slide.left - outer.left + box.x * scale) + 'px',
      top: (slide.top - outer.top + box.y * scale) + 'px', width: box.width * scale + 'px', height: box.height * scale + 'px'});
  }

  function removeFrame() {
    follow?.disconnect(); follow = null;
    frame?.remove(); frame = null;
  }

  function buildFrame(list: TransformTarget[], identity: string) {
    removeFrame();
    const lead = list[list.length - 1], label = list.length > 1 ? 'selection' : lead.label;
    const element = document.createElement('div');
    element.className = 'transform-frame' + (list.length > 1 ? ' transform-frame-group' : '');
    element.dataset.transformFrame = identity;
    element.dataset.transformControl = '';
    const grip = control('transform-move-grip', 'Move ' + label, 'Drag to move');
    grip.addEventListener('pointerdown', event => pointerDown(lead, event, 'move'));
    element.appendChild(grip);
    // The border is a move surface, so text being edited and charts that
    // keep their own drags can still be moved directly.
    ['top', 'right', 'bottom', 'left'].forEach(side => {
      const edge = document.createElement('div');
      edge.className = 'transform-edge transform-edge-' + side;
      edge.dataset.transformControl = '';
      edge.addEventListener('pointerdown', event => pointerDown(lead, event, 'move'));
      element.appendChild(edge);
    });
    if (list.every(t => t.resizable !== false)) HANDLES.forEach(handle => {
      // The bottom-right corner keeps the historical accessible name.
      const name = handle === 'se' ? 'Resize ' + label : 'Resize ' + label + ' from ' + HANDLE_NAMES[handle];
      const button = control('transform-handle transform-handle-' + handle, name, 'Drag to resize; Shift keeps proportions; Alt ignores guides');
      button.dataset.handle = handle;
      button.addEventListener('pointerdown', event => pointerDown(lead, event, handle));
      element.appendChild(button);
    });
    element.addEventListener('click', event => event.stopPropagation());
    // Outside the clipped slide, so handles on objects at the edge stay reachable.
    frameHost(lead.canvas).appendChild(element);
    frame = element;
    if (window.ResizeObserver) {
      follow = new ResizeObserver(() => requestAnimationFrame(sync));
      list.forEach(target => target.hits.forEach(node => follow!.observe(node)));
    }
  }
  function control(className: string, label: string, title: string) {
    const button = document.createElement('button');
    button.type = 'button'; button.className = className; button.tabIndex = -1;
    button.setAttribute('aria-label', label); button.title = title;
    button.dataset.transformControl = '';
    return button;
  }

  /** Keep the frame (and member outlines for a group) on the selection. */
  function sync() {
    const list = members();
    if (!list.length || !host.isEditMode()) { removeFrame(); return; }
    const identity = list.map(t => t.key).join('|'), canvas = list[0].canvas;
    if (!frame || frame.dataset.transformFrame !== identity || frame.parentElement !== frameHost(canvas)) buildFrame(list, identity);
    const boxes = list.map(boundsOf);
    place(frame!, canvas, unionBox(boxes));
    frame!.querySelectorAll('.transform-member').forEach(node => node.remove());
    if (list.length > 1) boxes.forEach(box => {
      const outline = document.createElement('div'); outline.className = 'transform-member';
      const union = unionBox(boxes), scale = canvasScale(canvas);
      Object.assign(outline.style, {left: (box.x - union.x) * scale + 'px', top: (box.y - union.y) * scale + 'px',
        width: box.width * scale + 'px', height: box.height * scale + 'px'});
      frame!.appendChild(outline);
    });
  }

  function drawGuides(canvas: HTMLElement | null, guides: Guide[], spacing: Spacing[]) {
    overlay?.remove(); overlay = null;
    if (!canvas || (!guides.length && !spacing.length)) return;
    overlay = document.createElement('div'); overlay.className = 'transform-guides'; overlay.dataset.transformControl = '';
    const container = frameHost(canvas); container.appendChild(overlay);
    guides.forEach(guide => {
      const line = document.createElement('div'); line.className = 'transform-guide transform-guide-' + guide.axis;
      place(line, canvas, guide.axis === 'x' ? {x: guide.at, y: guide.from, width: 0, height: guide.to - guide.from}
        : {x: guide.from, y: guide.at, width: guide.to - guide.from, height: 0});
      overlay!.appendChild(line);
    });
    spacing.forEach(bar => {
      const element = document.createElement('div'); element.className = 'transform-spacing transform-spacing-' + bar.axis;
      element.dataset.gap = String(Math.round(bar.end - bar.start));
      place(element, canvas, bar.axis === 'x' ? {x: bar.start, y: bar.cross, width: bar.end - bar.start, height: 0}
        : {x: bar.cross, y: bar.start, width: 0, height: bar.end - bar.start});
      overlay!.appendChild(element);
    });
  }

  // --- commands on the selection -------------------------------------------
  /** Apply new boxes to the selection as one undoable change. */
  function applyBoxes(list: TransformTarget[], boxes: Box[], group: string) {
    host.beginChange(group);
    list.forEach((target, index) => {
      const edit = target.edit();
      edit.update(roundBox(inside(boxes[index], target.area?.() || SLIDE))); edit.finish?.();
    });
    host.persist();
    sync();
  }

  /** Arrow keys move the selection; returns whether the key was used. */
  function nudge(event: KeyboardEvent): boolean {
    const list = members();
    if (!list.length || !host.isEditMode() || event.metaKey || event.ctrlKey || event.altKey) return false;
    const boxes = list.map(boundsOf), union = unionBox(boxes);
    const next = nudgeBox(union, event.key, event.shiftKey, list.length === 1 ? list[0].area?.() || SLIDE : SLIDE);
    if (!next) return false;
    applyBoxes(list, boxes.map(box => ({...box, x: box.x + next.x - union.x, y: box.y + next.y - union.y})),
      groupOf(list) + ':nudge');
    return true;
  }
  function align(mode: Alignment) {
    const list = members();
    if (!list.length) return false;
    applyBoxes(list, alignBoxes(list.map(boundsOf), mode, SLIDE), groupOf(list) + ':align');
    return true;
  }
  function distribute(axis: 'x' | 'y') {
    const list = members();
    if (list.length < 3) return false;
    applyBoxes(list, distributeBoxes(list.map(boundsOf), axis), groupOf(list) + ':distribute');
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
    if (target) pointerDown(target, event, 'move');
  }

  return {register, select, toggle, selectAll, marquee, sync, nudge, align, distribute, clear, grab,
    /** True while the press that produced the current click belonged to an object. */
    ownsPress: () => ownsPress,
    selected: () => selection.length ? selection[selection.length - 1] : null,
    keys: () => selection.slice(),
    identities: () => members().map(t => t.identity).filter((id): id is TargetIdentity => Boolean(id)),
    has: (key: string) => targets.has(key),
    unregister(key: string) { targets.delete(key); if (selection.includes(key)) setSelection(selection.filter(k => k !== key)); }};
}
export type TransformLayer = ReturnType<typeof createTransformLayer>;

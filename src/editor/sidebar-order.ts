import Sortable, {MultiDrag} from 'sortablejs/modular/sortable.esm.js';

Sortable.mount(new MultiDrag());

interface OrderHost {
  order(): readonly string[];
  move(ids: string[], before: string | null): void;
  refresh(): void;
  announce(message: string): void;
}

/** Sortable owns the transient gesture; the existing state queue owns saving.
 * Freeze rail reconciliation (not saves) until the library has released its
 * DOM. A concurrent authoritative order change cancels the stale gesture.
 */
export function createSidebarOrder(list: HTMLElement, host: OrderHost) {
  let active = false, cancelled = false, base: string[] = [], suppressUntil = 0;
  const labelOnly = (copy: HTMLElement | null) => {
    if (!copy) return;
    copy.querySelectorAll('iframe').forEach(frame => frame.remove());
    copy.querySelectorAll('.preview-ready').forEach(art => art.classList.remove('preview-ready'));
  };
  const sortable = new Sortable(list, {
    draggable: '.thumb', dataIdAttr: 'data-id',
    multiDrag: true, multiDragKey: 'SHIFT', selectedClass: 'thumb-selected',
    filter: 'button, input, a', preventOnFilter: false,
    animation: 140, forceFallback: true, fallbackOnBody: true,
    fallbackTolerance: 6, delay: 180, delayOnTouchOnly: true,
    touchStartThreshold: 5, scroll: true, scrollSensitivity: 65, scrollSpeed: 14,
    ghostClass: 'thumb-drop-slot', chosenClass: 'thumb-picked', fallbackClass: 'thumb-drag-copy',
    onClone(event) {
      labelOnly(event.clone);
      const clones = (event as Sortable.SortableEvent & {clones?: HTMLElement[]}).clones;
      (clones || []).forEach(labelOnly);
    },
    onStart() {
      base = [...host.order()]; active = true; cancelled = false;
      list.classList.add('reordering');
      if (Sortable.ghost) labelOnly(Sortable.ghost);
    },
    onEnd(event) {
      const ids = sortable.toArray();
      const moving = (event.items.length ? event.items : [event.item])
        .map(item => item.dataset.id).filter((id): id is string => !!id);
      const last = Math.max(...moving.map(id => ids.indexOf(id)));
      suppressUntil = performance.now() + 200;
      queueMicrotask(() => {
        active = false; list.classList.remove('reordering');
        if (cancelled || JSON.stringify(base) !== JSON.stringify(host.order())) {
          host.announce(cancelled ? 'Slide move cancelled.' : 'Order changed during drag; please drag again.');
        } else if (moving.length && last >= 0 && JSON.stringify(ids) !== JSON.stringify(base)) {
          host.move(moving, ids[last + 1] || null);
        }
        host.refresh();
      });
    }
  });
  const cancel = (event: KeyboardEvent) => {
    if (active && event.key === 'Escape') {
      cancelled = true; event.preventDefault(); event.stopImmediatePropagation();
    } else if (event.key === 'Escape') {
      list.querySelectorAll<HTMLElement>('.thumb-selected').forEach(item => Sortable.utils.deselect(item));
    }
  };
  const suppressClick = (event: MouseEvent) => {
    if (active || performance.now() < suppressUntil || (event.shiftKey &&
        !(event.target as Element).closest('button, input, a'))) {
      event.preventDefault(); event.stopImmediatePropagation();
    }
  };
  const cancelPointer = () => { if (active) cancelled = true; };
  document.addEventListener('keydown', cancel, true);
  document.addEventListener('pointercancel', cancelPointer, true);
  document.addEventListener('touchcancel', cancelPointer, true);
  list.addEventListener('click', suppressClick, true);
  return {
    active: () => active,
    destroy() {
      sortable.destroy(); document.removeEventListener('keydown', cancel, true);
      document.removeEventListener('pointercancel', cancelPointer, true);
      document.removeEventListener('touchcancel', cancelPointer, true);
      list.removeEventListener('click', suppressClick, true);
    }
  };
}

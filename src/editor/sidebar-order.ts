import Sortable from 'sortablejs';

interface OrderHost {
  order(): readonly string[];
  move(id: string, before: string | null): void;
  refresh(): void;
  announce(message: string): void;
}

/** Sortable owns the transient gesture; the existing state queue owns saving.
 * Freeze rail reconciliation (not saves) until the library has released its
 * DOM. A concurrent authoritative order change cancels the stale gesture.
 */
export function createSidebarOrder(list: HTMLElement, host: OrderHost) {
  let active = false, cancelled = false, base: string[] = [], suppressUntil = 0;
  const labelOnly = (copy: HTMLElement) => {
    copy.querySelectorAll('iframe').forEach(frame => frame.remove());
    copy.querySelectorAll('.preview-ready').forEach(art => art.classList.remove('preview-ready'));
  };
  const sortable = new Sortable(list, {
    draggable: '.thumb', dataIdAttr: 'data-id',
    filter: 'button, input, a', preventOnFilter: false,
    animation: 140, forceFallback: true, fallbackOnBody: true,
    fallbackTolerance: 6, delay: 180, delayOnTouchOnly: true,
    touchStartThreshold: 5, scroll: true, scrollSensitivity: 65, scrollSpeed: 14,
    ghostClass: 'thumb-drop-slot', chosenClass: 'thumb-picked', fallbackClass: 'thumb-drag-copy',
    onClone(event) { labelOnly(event.clone); },
    onStart() {
      base = [...host.order()]; active = true; cancelled = false;
      list.classList.add('reordering');
      if (Sortable.ghost) labelOnly(Sortable.ghost);
    },
    onEnd(event) {
      const ids = sortable.toArray(), id = event.item.dataset.id;
      const index = id ? ids.indexOf(id) : -1;
      suppressUntil = performance.now() + 200;
      queueMicrotask(() => {
        active = false; list.classList.remove('reordering');
        if (cancelled || JSON.stringify(base) !== JSON.stringify(host.order())) {
          host.announce(cancelled ? 'Slide move cancelled.' : 'Order changed during drag; please drag again.');
        } else if (id && index >= 0 && JSON.stringify(ids) !== JSON.stringify(base)) {
          host.move(id, ids[index + 1] || null);
        }
        host.refresh();
      });
    }
  });
  const cancel = (event: KeyboardEvent) => {
    if (active && event.key === 'Escape') {
      cancelled = true; event.preventDefault(); event.stopImmediatePropagation();
    }
  };
  const suppressClick = (event: MouseEvent) => {
    if (active || performance.now() < suppressUntil) {
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

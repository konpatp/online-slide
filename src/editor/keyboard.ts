/** Text fields own character deletion. Whole-object keys only run outside them. */
export function typingTarget(target: EventTarget | null): boolean {
  return target instanceof Element && Boolean(target.closest('input, textarea, select, [role="textbox"]') ||
    (target as HTMLElement).isContentEditable);
}
export function deletionKey(event: KeyboardEvent): boolean {
  return !event.defaultPrevented && !event.isComposing && !event.repeat &&
    !event.metaKey && !event.ctrlKey && !event.altKey && !event.shiftKey &&
    ['Delete','Backspace'].includes(event.key) && !typingTarget(event.target);
}

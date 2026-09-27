/** Text formatting commands for the selected text component.
 *
 * A command applies to the selected characters; with only a caret, to all
 * of the object's text (character styles; a table cell's whole value) or the
 * caret's line (paragraph settings); with the object selected and no text
 * focused, to all of its text and lines. Every command
 * is one undoable change and keeps the user's text selection.
 */
import type {Paragraph, RichText} from './model';
import {rangeHas, readRichText, renderRichText, selectionOffsets, setMark, setParagraphs,
  setSelectionOffsets, splice, toggleMark, attrsOf, paragraphsOf, lineAt} from './text';
import {richFromHtml} from './paste';

interface FormattingHost {
  isEditMode(): boolean;
  selected(): {slideId: string; componentId: string} | null;
  element(slideId: string, componentId: string): HTMLElement | null;
  beginChange(group?: string): void;
  persist(): void;
  updateText(slideId: string, componentId: string, value: RichText): void;
  /** Whole-object styles that predate character formatting. */
  componentStyle(slideId: string, componentId: string): {color?: string; fontScale?: number};
  setComponentStyle(slideId: string, componentId: string, key: 'color' | 'fontScale', value: string | number | undefined): void;
  refreshTools(): void;
}
export interface Scope {
  slideId: string; componentId: string; element: HTMLElement; value: RichText;
  start: number; end: number;
  /** True when the whole object is the target (no text focused). */
  whole: boolean;
  /** Where to put the text selection back afterwards. */
  restore: {start: number; end: number} | null;
}

export function createTextFormatting(host: FormattingHost) {
  let pinned: Scope | null = null;
  // The last text selection, so controls that take focus (colour, size) can
  // still format it after the text itself has lost focus.
  let remembered: {slideId: string; componentId: string; start: number; end: number} | null = null;

  /** Resolve what a command applies to, or null when no plain text is selected. */
  function scope(useRemembered = false): Scope | null {
    if (pinned) return pinned;
    const chosen = host.selected();
    if (!chosen || !host.isEditMode()) return null;
    const element = host.element(chosen.slideId, chosen.componentId);
    if (!element || element.dataset.latexSource !== undefined || !element.isContentEditable) return null;
    const value = readRichText(element);
    const focused = document.activeElement === element || element.contains(document.activeElement);
    let offsets = focused ? selectionOffsets(element) : null;
    // A control that took focus still sees the text's own selection, which is
    // current; the remembered copy (updated asynchronously) is only a fallback.
    if (!offsets && useRemembered) offsets = selectionOffsets(element);
    if (!offsets && useRemembered && remembered && remembered.slideId === chosen.slideId &&
        remembered.componentId === chosen.componentId && remembered.end <= value.text.length)
      offsets = {start: remembered.start, end: remembered.end};
    if (!offsets) return {...chosen, element, value, start: 0, end: value.text.length, whole: true, restore: null};
    // Caret only: character styles cover the whole text (paragraph commands
    // use the caret's line through `restore`).
    const {start, end} = offsets.start === offsets.end ? {start: 0, end: value.text.length} : offsets;
    return {...chosen, element, value, start, end, whole: false, restore: offsets};
  }
  /** Keep the scope while a control that takes focus (colour, size) is open. */
  function pin() { pinned = null; pinned = scope(true); }
  function unpin() { pinned = null; }
  /** Called as the document selection changes. */
  function remember() {
    const chosen = host.selected(), element = chosen && host.element(chosen.slideId, chosen.componentId);
    if (!chosen || !element || !(document.activeElement === element || element.contains(document.activeElement))) return;
    const offsets = selectionOffsets(element);
    if (offsets) remembered = {slideId: chosen.slideId, componentId: chosen.componentId, ...offsets};
  }

  function commit(target: Scope, next: RichText, restore = target.restore, group?: string) {
    host.beginChange(group);
    host.updateText(target.slideId, target.componentId, next);
    renderRichText(target.element, next);
    if (restore) { target.element.focus({preventScroll: true}); setSelectionOffsets(target.element, restore.start, restore.end); }
    host.persist();
    host.refreshTools();
  }
  const inherited = (element: HTMLElement, key: 'bold' | 'italic' | 'underline') => {
    const style = getComputedStyle(element);
    return key === 'bold' ? Number(style.fontWeight) >= 600 : key === 'italic' ? style.fontStyle === 'italic'
      : style.textDecorationLine.includes('underline');
  };

  function toggle(key: 'bold' | 'italic' | 'underline') {
    const target = scope();
    if (!target || target.end <= target.start) return false;
    commit(target, toggleMark(target.value, target.start, target.end, key, inherited(target.element, key)));
    return true;
  }
  /** All of an object's text uses the object's own colour and size, not marks. */
  const allText = (target: Scope) => target.whole || (target.start === 0 && target.end === target.value.text.length);
  /** Colour: selected characters get a mark; all of the text keeps the object's style. */
  function color(value: string) {
    const target = scope();
    if (!target) return false;
    if (allText(target)) {
      host.beginChange(); host.setComponentStyle(target.slideId, target.componentId, 'color', value);
      // Whole-object colour replaces character colours inside it.
      const cleared = setMark(target.value, 0, target.value.text.length, 'color', undefined);
      host.updateText(target.slideId, target.componentId, cleared); renderRichText(target.element, cleared);
      target.element.style.color = value; host.persist(); host.refreshTools(); return true;
    }
    if (target.end <= target.start) return false;
    commit(target, setMark(target.value, target.start, target.end, 'color', value));
    return true;
  }
  /** Size as a percentage of the element's own size (auto-fit still applies). */
  function currentSize(target: Scope): number {
    if (allText(target)) return Math.round((host.componentStyle(target.slideId, target.componentId).fontScale || 1) * 100);
    const sizes = attrsOf(target.value).slice(target.start, Math.max(target.end, target.start + 1)).map(a => a.size ?? 1);
    return Math.round((sizes[0] ?? 1) * 100);
  }
  function size(percent: number) {
    const target = scope();
    if (!target || !Number.isFinite(percent)) return false;
    if (allText(target)) {
      const scale = Math.max(.7, Math.min(1.5, Math.round(percent) / 100));
      host.beginChange(); host.setComponentStyle(target.slideId, target.componentId, 'fontScale', scale === 1 ? undefined : scale);
      host.persist(); host.refreshTools(); return true;
    }
    if (target.end <= target.start) return false;
    const factor = Math.max(.5, Math.min(3, Math.round(percent) / 100));
    commit(target, setMark(target.value, target.start, target.end, 'size', factor === 1 ? undefined : factor));
    return true;
  }
  function resize(deltaPercent: number) {
    const target = scope();
    return target ? size(currentSize(target) + deltaPercent) : false;
  }

  // --- paragraphs -----------------------------------------------------------
  /** Paragraph settings need block layout; inline labels (legend entries,
   * table cells) keep their single-line flow. */
  const paragraphCapable = (element: HTMLElement) => getComputedStyle(element).display !== 'inline'
    && !element.closest('[data-table-cell]');
  function paragraphs(patch: (p: Paragraph) => Paragraph) {
    const target = scope();
    if (!target || !paragraphCapable(target.element)) return false;
    const {start, end} = target.whole ? {start: 0, end: target.value.text.length} : target.restore || target;
    commit(target, setParagraphs(target.value, start, end, patch));
    return true;
  }
  const align = (mode: 'left' | 'center' | 'right') => paragraphs(p => ({...p, align: mode}));
  function list(kind: 'bullet' | 'number') {
    const target = scope();
    if (!target) return false;
    const line = lineAt(target.value.text, (target.restore || target).start);
    const on = paragraphsOf(target.value)[line]?.list === kind;
    return paragraphs(p => on ? {...p, list: undefined, level: undefined} : {...p, list: kind});
  }
  function indent(delta: number) {
    return paragraphs(p => {
      if (!p.list) return p;
      const level = (p.level || 0) + delta;
      return level < 0 ? {...p, list: undefined, level: undefined} : {...p, level: Math.min(2, level)};
    });
  }

  // --- typing boundaries ----------------------------------------------------
  /** Replace the text selection with rich text, as one model-level edit. */
  function insert(element: HTMLElement, slideId: string, componentId: string, rich: RichText, group?: string) {
    const value = readRichText(element), offsets = selectionOffsets(element) || {start: value.text.length, end: value.text.length};
    const next = splice(value, offsets.start, offsets.end, rich);
    const caret = offsets.start + rich.text.length;
    commit({slideId, componentId, element, value, start: offsets.start, end: offsets.end, whole: false, restore: null},
      next, {start: caret, end: caret}, group);
  }
  /** Enter: a new line continues its list; Enter on an empty list line ends the list. */
  function enter(element: HTMLElement, slideId: string, componentId: string) {
    const value = readRichText(element), offsets = selectionOffsets(element);
    if (offsets && offsets.start === offsets.end) {
      const line = lineAt(value.text, offsets.start), lines = value.text.split('\n');
      const paragraph = paragraphsOf(value)[line];
      if (paragraph?.list && !lines[line].length) {
        const next = setParagraphs(value, offsets.start, offsets.start, p => ({...p, list: undefined, level: undefined}));
        commit({slideId, componentId, element, value, start: offsets.start, end: offsets.end, whole: false, restore: offsets}, next);
        return;
      }
    }
    insert(element, slideId, componentId, {text: '\n', marks: []}, 'text:' + slideId + ':' + componentId);
  }
  /** Paste keeps bold, italic, underline, line breaks and lists; drops the rest. */
  function paste(event: ClipboardEvent, element: HTMLElement, slideId: string, componentId: string) {
    const html = event.clipboardData?.getData('text/html');
    const text = event.clipboardData?.getData('text/plain');
    if (!html && (text === undefined || text === null)) return false;
    event.preventDefault();
    let rich = html ? richFromHtml(html) : {text: (text || '').replace(/\r\n?/g, '\n'), marks: []};
    if (!paragraphCapable(element)) rich = {text: rich.text, marks: rich.marks};
    insert(element, slideId, componentId, rich);
    return true;
  }

  /** Standard shortcuts inside editable text; returns whether it was handled. */
  function key(event: KeyboardEvent, element: HTMLElement): boolean {
    if (event.isComposing) return false;
    const mod = event.metaKey || event.ctrlKey, k = event.key.toLowerCase();
    if (mod && !event.shiftKey && !event.altKey && (k === 'b' || k === 'i' || k === 'u'))
      return toggle(k === 'b' ? 'bold' : k === 'i' ? 'italic' : 'underline');
    if (mod && event.shiftKey && (event.code === 'Digit7' || event.code === 'Digit8'))
      return list(event.code === 'Digit7' ? 'number' : 'bullet');
    if (mod && event.shiftKey && (k === 'l' || k === 'e' || k === 'r'))
      return align(k === 'l' ? 'left' : k === 'e' ? 'center' : 'right');
    if (event.key === 'Tab' && !mod && !event.altKey && !element.closest('[data-table-cell]')) {
      const value = readRichText(element), offsets = selectionOffsets(element);
      if (!offsets || !paragraphsOf(value)[lineAt(value.text, offsets.start)]?.list) return false;
      return indent(event.shiftKey ? -1 : 1);
    }
    return false;
  }

  /** Pressed and current values for the toolbar. */
  function toolState() {
    const target = scope();
    if (!target) return null;
    const range = {start: target.start, end: Math.max(target.end, target.start)};
    const lines = paragraphsOf(target.value);
    const line = lines[lineAt(target.value.text, (target.restore || target).start)] || {};
    return {
      bold: rangeHas(target.value, range.start, range.end, 'bold', inherited(target.element, 'bold')),
      italic: rangeHas(target.value, range.start, range.end, 'italic', inherited(target.element, 'italic')),
      underline: rangeHas(target.value, range.start, range.end, 'underline', inherited(target.element, 'underline')),
      size: currentSize(target), align: line.align || 'left', list: line.list || null,
      paragraphs: paragraphCapable(target.element),
      color: allText(target) ? host.componentStyle(target.slideId, target.componentId).color
        : attrsOf(target.value)[target.start]?.color};
  }

  return {scope, pin, unpin, remember, toggle, color, size, resize, align, list, indent, insert, enter, paste, key, toolState};
}
export type TextFormatting = ReturnType<typeof createTextFormatting>;

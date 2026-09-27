import type { Paragraph, RichText, TextMark, TextOverlay } from './model';

/** Rich text is plain wording plus two kinds of validated attributes:
 * character ranges (`marks`) and per-line paragraph settings. Never HTML.
 * Offsets are DOM UTF-16 units; paragraphs align one-to-one with lines. */
export type MarkKey = 'bold' | 'italic' | 'underline' | 'color' | 'size';
export type Attrs = Partial<Pick<TextMark, MarkKey>>;
const KEYS: readonly MarkKey[] = ['bold', 'italic', 'underline', 'color', 'size'];
const same = (a: Attrs, b: Attrs) => KEYS.every(key => a[key] === b[key]);
const empty = (a: Attrs) => KEYS.every(key => a[key] === undefined);
const cleanParagraph = (p: Paragraph): Paragraph => {
  const out: Paragraph = {};
  if (p.align && p.align !== 'left') out.align = p.align;
  if (p.list) { out.list = p.list; if (p.level) out.level = p.level; }
  return out;
};
const plain = (p: Paragraph) => !p.align && !p.list;

/** Formatting and its exact wording travel together as one edit. */
export function textEdit(value: RichText): TextOverlay {
  const edit: TextOverlay = {text: value.text, marks: value.marks.map(mark => ({...mark}))};
  const paragraphs = compactParagraphs(value.text, value.paragraphs);
  if (paragraphs) edit.paragraphs = paragraphs;
  return edit;
}

// --- characters -------------------------------------------------------------
export function attrsOf(value: RichText): Attrs[] {
  const out: Attrs[] = Array.from({length: value.text.length}, () => ({}));
  for (const mark of value.marks || []) for (let i = mark.start; i < mark.end && i < out.length; i++)
    for (const key of KEYS) if (mark[key] !== undefined) (out[i] as Record<string, unknown>)[key] = mark[key];
  return out;
}
export function marksOf(attrs: Attrs[]): TextMark[] {
  const marks: TextMark[] = [];
  attrs.forEach((a, index) => {
    if (empty(a)) return;
    const last = marks[marks.length - 1];
    if (last && last.end === index && same(last, a)) last.end++;
    else {
      const mark: TextMark = {start: index, end: index + 1};
      for (const key of KEYS) if (a[key] !== undefined) (mark as unknown as Record<string, unknown>)[key] = a[key];
      marks.push(mark);
    }
  });
  return marks;
}
/** Set (or with `undefined`, clear) one attribute over a range. */
export function setMark<K extends MarkKey>(value: RichText, start: number, end: number, key: K, next: TextMark[K] | undefined): RichText {
  const attrs = attrsOf(value);
  for (let i = start; i < end; i++) {
    if (next === undefined) delete attrs[i][key]; else attrs[i][key] = next;
  }
  return {...value, marks: marksOf(attrs)};
}
/** Bold/italic/underline: on if any character in range is off, else off.
 * `inherited` is the style the element shows without a mark (headings are bold). */
export function toggleMark(value: RichText, start: number, end: number, key: 'bold' | 'italic' | 'underline', inherited: boolean): RichText {
  const attrs = attrsOf(value);
  const on = !attrs.slice(start, end).every(a => a[key] ?? inherited);
  return setMark(value, start, end, key, on);
}
/** Whether every character of a range shows an attribute (for pressed buttons). */
export function rangeHas(value: RichText, start: number, end: number, key: 'bold' | 'italic' | 'underline', inherited: boolean): boolean {
  const attrs = attrsOf(value).slice(start, Math.max(end, start + 1));
  return attrs.length > 0 && attrs.every(a => a[key] ?? inherited);
}

// --- paragraphs -------------------------------------------------------------
export const lineCount = (text: string) => text.split('\n').length;
export function lineAt(text: string, offset: number): number {
  let line = 0;
  for (let i = 0; i < offset && i < text.length; i++) if (text[i] === '\n') line++;
  return line;
}
export function paragraphsOf(value: RichText): Paragraph[] {
  const count = lineCount(value.text);
  return Array.from({length: count}, (_, i) => ({...(value.paragraphs?.[i] || {})}));
}
export function compactParagraphs(text: string, paragraphs: Paragraph[] | undefined): Paragraph[] | undefined {
  if (!paragraphs) return undefined;
  const count = lineCount(text);
  const out = Array.from({length: count}, (_, i) => cleanParagraph(paragraphs[i] || {}));
  return out.every(plain) ? undefined : out;
}
/** Change the paragraphs of every line the range touches. */
export function setParagraphs(value: RichText, start: number, end: number, patch: (p: Paragraph) => Paragraph): RichText {
  const ps = paragraphsOf(value), first = lineAt(value.text, start), last = lineAt(value.text, Math.max(start, end));
  for (let i = first; i <= last; i++) ps[i] = cleanParagraph(patch(ps[i]));
  return {...value, paragraphs: compactParagraphs(value.text, ps)};
}

/** Replace `start..end` with `insert`. Characters keep their attributes; new
 * lines continue the paragraph they split (so Enter in a list continues it)
 * unless the insert brings its own paragraphs (a pasted list). */
export function splice(value: RichText, start: number, end: number, insert: RichText): RichText {
  const attrs = attrsOf(value);
  // Plain text takes the style around it; rich text brings its own.
  const around = attrs[start - 1] ?? attrs[end] ?? {};
  const added = insert.marks?.length ? attrsOf(insert)
    : Array.from(insert.text, ch => ch === '\n' ? {} : {...around});
  const text = value.text.slice(0, start) + insert.text + value.text.slice(end);
  const nextAttrs = [...attrs.slice(0, start), ...added, ...attrs.slice(end)];
  const ps = paragraphsOf(value), first = lineAt(value.text, start), last = lineAt(value.text, end);
  const incoming = lineCount(insert.text), own = insert.paragraphs;
  const atLineStart = start === 0 || value.text[start - 1] === '\n';
  const middle = Array.from({length: incoming}, (_, i) => {
    if (own?.[i] && (i > 0 || atLineStart) && !plain(own[i])) return {...own[i]};
    return i === 0 ? ps[first] : {...(own ? {} : ps[first])};
  });
  const paragraphs = [...ps.slice(0, first), ...middle, ...ps.slice(last + 1)];
  return {text, marks: marksOf(nextAttrs), paragraphs: compactParagraphs(text, paragraphs)};
}

// --- rendering --------------------------------------------------------------
const BULLETS = ['•', '◦', '▪'];
function applyAttrs(span: HTMLElement, a: Attrs) {
  if (a.bold !== undefined) { span.dataset.textBold = String(a.bold); span.style.fontWeight = a.bold ? '700' : '400'; }
  if (a.italic !== undefined) { span.dataset.textItalic = String(a.italic); span.style.fontStyle = a.italic ? 'italic' : 'normal'; }
  if (a.underline !== undefined) { span.dataset.textUnderline = String(a.underline); span.style.textDecoration = a.underline ? 'underline' : 'none'; }
  if (a.color !== undefined) { span.dataset.textColor = a.color; span.style.color = a.color; }
  if (a.size !== undefined) { span.dataset.textSize = String(a.size); span.style.fontSize = a.size + 'em'; }
}
function appendRuns(parent: HTMLElement, value: RichText, from: number, to: number) {
  let offset = from;
  // Authored text may carry no marks at all.
  for (const mark of value.marks || []) {
    const start = Math.max(mark.start, from), end = Math.min(mark.end, to);
    if (end <= start) continue;
    if (start > offset) parent.appendChild(document.createTextNode(value.text.slice(offset, start)));
    const span = document.createElement('span');
    applyAttrs(span, mark);
    span.textContent = value.text.slice(start, end);
    parent.appendChild(span); offset = end;
  }
  if (offset < to) parent.appendChild(document.createTextNode(value.text.slice(offset, to)));
}
/** Lines render as blocks only once a paragraph is aligned or listed, so all
 * existing text keeps its exact inline rendering. */
export function renderRichText(element: HTMLElement, component: RichText): void {
  element.textContent = '';
  const paragraphs = compactParagraphs(component.text, component.paragraphs);
  if (!paragraphs) {
    appendRuns(element, component, 0, component.text.length);
    if (component.text.endsWith('\n')) element.appendChild(document.createElement('br'));
    return;
  }
  element.classList.add('rich-paragraphs');
  const lines = component.text.split('\n');
  const counters = [0, 0, 0];
  let offset = 0;
  lines.forEach((line, index) => {
    const p = paragraphs[index], div = document.createElement('div');
    div.className = 'text-line';
    if (p.align) div.dataset.align = p.align;
    if (p.list) {
      const level = p.level || 0;
      div.dataset.list = p.list; div.dataset.level = String(level);
      counters.fill(0, level + 1);
      if (p.list === 'number') div.dataset.marker = ++counters[level] + '.';
      else { counters[level] = 0; div.dataset.marker = BULLETS[level]; }
    } else counters.fill(0);
    appendRuns(div, component, offset, offset + line.length);
    if (!line.length) div.appendChild(document.createElement('br'));
    element.appendChild(div);
    offset += line.length + 1;
  });
}

// --- reading back from the editable DOM -------------------------------------
const lineBlocks = (element: HTMLElement) => Array.from(element.children).filter(
  (child): child is HTMLElement => child instanceof HTMLElement && child.classList.contains('text-line'));
function readAttrs(node: Node, root: HTMLElement): Attrs {
  const a: Attrs = {};
  for (let el = node.parentElement; el && el !== root && root.contains(el); el = el.parentElement) {
    const d = el.dataset, tag = el.tagName;
    if (a.bold === undefined) { if (d.textBold !== undefined) a.bold = d.textBold !== 'false'; else if (tag === 'B' || tag === 'STRONG') a.bold = true; }
    if (a.italic === undefined) { if (d.textItalic !== undefined) a.italic = d.textItalic !== 'false'; else if (tag === 'I' || tag === 'EM') a.italic = true; }
    if (a.underline === undefined) { if (d.textUnderline !== undefined) a.underline = d.textUnderline !== 'false'; else if (tag === 'U') a.underline = true; }
    if (a.color === undefined && d.textColor) a.color = d.textColor;
    if (a.size === undefined && d.textSize) a.size = Number(d.textSize);
  }
  return a;
}
function readRuns(container: HTMLElement, root: HTMLElement, text: string[], attrs: Attrs[]) {
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  let node: Node | null;
  while ((node = walker.nextNode())) {
    const value = node.textContent || '', a = readAttrs(node, root);
    text.push(value);
    for (let i = 0; i < value.length; i++) attrs.push(value[i] === '\n' ? {} : {...a});
  }
}
const paragraphOf = (div: HTMLElement): Paragraph => cleanParagraph({
  align: div.dataset.align as Paragraph['align'], list: div.dataset.list as Paragraph['list'],
  level: div.dataset.level ? Number(div.dataset.level) : undefined});
export function readRichText(element: HTMLElement): RichText {
  const blocks = lineBlocks(element), text: string[] = [], attrs: Attrs[] = [];
  if (!blocks.length) {
    readRuns(element, element, text, attrs);
    return {text: text.join(''), marks: marksOf(attrs)};
  }
  const paragraphs: Paragraph[] = [];
  blocks.forEach((div, index) => {
    if (index) { text.push('\n'); attrs.push({}); }
    const before = text.join('').length;
    readRuns(div, element, text, attrs);
    const inner = text.join('').slice(before);
    // Text typed into a line may itself contain new lines; they inherit it.
    for (let i = 0; i < lineCount(inner); i++) paragraphs.push(paragraphOf(div));
  });
  const joined = text.join('');
  return {text: joined, marks: marksOf(attrs), paragraphs: compactParagraphs(joined, paragraphs)};
}

// --- caret and selection offsets ------------------------------------------
/** Model offset of a DOM point inside the element. */
export function offsetAt(element: HTMLElement, node: Node, nodeOffset: number): number {
  const blocks = lineBlocks(element);
  const prefix = document.createRange(); prefix.selectNodeContents(element);
  if (!blocks.length) { prefix.setEnd(node, nodeOffset); return prefix.toString().length; }
  let offset = 0;
  for (const div of blocks) {
    if (div === node || div.contains(node)) {
      const inner = document.createRange(); inner.selectNodeContents(div); inner.setEnd(node, nodeOffset);
      return offset + inner.toString().length;
    }
    const range = document.createRange(); range.selectNodeContents(div);
    if (range.comparePoint(node, nodeOffset) < 0) return offset;
    offset += (div.textContent || '').length + 1;
  }
  return Math.max(0, offset - 1);
}
/** The element's current selection as model offsets, or null if elsewhere. */
export function selectionOffsets(element: HTMLElement): {start: number; end: number} | null {
  const selection = getSelection();
  if (!selection?.rangeCount) return null;
  const range = selection.getRangeAt(0);
  if (!element.contains(range.startContainer) || !element.contains(range.endContainer)) return null;
  const start = offsetAt(element, range.startContainer, range.startOffset);
  const end = offsetAt(element, range.endContainer, range.endOffset);
  return {start: Math.min(start, end), end: Math.max(start, end)};
}
function pointAt(element: HTMLElement, offset: number): {node: Node; offset: number} {
  const blocks = lineBlocks(element);
  const containers: HTMLElement[] = blocks.length ? blocks : [element];
  let remaining = offset;
  for (const [index, container] of containers.entries()) {
    const length = (container.textContent || '').length;
    if (remaining <= length || index === containers.length - 1) {
      const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
      let node: Node | null, last: Node | null = null;
      while ((node = walker.nextNode())) {
        const size = (node.textContent || '').length;
        if (remaining <= size) return {node, offset: remaining};
        remaining -= size; last = node;
      }
      return last ? {node: last, offset: (last.textContent || '').length} : {node: container, offset: 0};
    }
    remaining -= length + 1;
  }
  return {node: element, offset: 0};
}
export function setSelectionOffsets(element: HTMLElement, start: number, end = start): void {
  const selection = getSelection();
  if (!selection) return;
  const a = pointAt(element, start), b = pointAt(element, end), range = document.createRange();
  range.setStart(a.node, a.offset); range.setEnd(b.node, b.offset);
  selection.removeAllRanges(); selection.addRange(range);
}

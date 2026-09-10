import type { RichText, TextMark, TextOverlay } from './model';

/** Formatting is a command over wording and ranges together. */
export function textEdit(value: RichText): TextOverlay {
  return {text: value.text, marks: value.marks.map(mark => ({...mark}))};
}
export function toggleBold(value: RichText, start: number, end: number, inherited: boolean): RichText {
  const flags: (boolean | null)[] = Array(value.text.length).fill(null);
  value.marks.forEach(mark => flags.fill(mark.bold, mark.start, mark.end));
  const makeBold = !flags.slice(start,end).every(flag => flag === null ? inherited : flag);
  flags.fill(makeBold, start, end);
  const marks: TextMark[] = [];
  flags.forEach((flag,index) => {
    if (flag === null) return;
    const last = marks[marks.length-1];
    if (last && last.end === index && last.bold === flag) last.end++;
    else marks.push({start:index, end:index+1, bold:flag});
  });
  return {text:value.text, marks};
}
export function renderMarkedText(element: HTMLElement, component: {text: string; marks?: TextMark[]}): void {
  element.textContent = '';
  let offset = 0;
  (component.marks || []).forEach(mark => {
    element.appendChild(document.createTextNode(component.text.slice(offset, mark.start)));
    const span = document.createElement('span');
    span.dataset.textBold = String(mark.bold);
    span.style.fontWeight = mark.bold ? '700' : '400';
    span.textContent = component.text.slice(mark.start,mark.end);
    element.appendChild(span); offset = mark.end;
  });
  element.appendChild(document.createTextNode(component.text.slice(offset)));
  if (component.text.endsWith('\n')) element.appendChild(document.createElement('br'));
}
export function readMarkedText(element: HTMLElement): RichText {
  const text = element.textContent || '';
  const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
  const marks: TextMark[] = [];
  let node: Node | null, offset = 0;
  while ((node = walker.nextNode())) {
    const owner = node.parentElement?.closest<HTMLElement>('[data-text-bold],b,strong');
    const start = offset, end = offset + (node.textContent || '').length;
    if (owner && element.contains(owner) && end > start) {
      const bold = owner.dataset.textBold !== 'false', last = marks[marks.length-1];
      if (last && last.end === start && last.bold === bold) last.end = end;
      else marks.push({start,end,bold});
    }
    offset = end;
  }
  return {text,marks};
}
export function insertPlainText(element: HTMLElement, text: string): void {
  const selection = getSelection();
  if (!selection?.rangeCount) return;
  const range = selection.getRangeAt(0);
  if (!element.contains(range.startContainer) || !element.contains(range.endContainer)) return;
  range.deleteContents();
  const node = document.createTextNode(text); range.insertNode(node);
  if (element.textContent?.endsWith('\n') && element.lastChild?.nodeName !== 'BR')
    element.appendChild(document.createElement('br'));
  range.setStart(node,node.length); range.collapse(true);
  selection.removeAllRanges(); selection.addRange(range);
  element.dispatchEvent(new Event('input',{bubbles:true}));
}

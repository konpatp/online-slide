/** Clipboard HTML → rich text. Keeps wording, line breaks, bold, italic,
 * underline and bullet/numbered lists (with nesting); drops every other
 * style, link, image and script. The result is plain data, never markup. */
import type {Paragraph, RichText} from './model';
import {marksOf, compactParagraphs} from './text';
import type {Attrs} from './text';

const BLOCK = new Set(['P', 'DIV', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'BLOCKQUOTE', 'PRE', 'SECTION',
  'ARTICLE', 'HEADER', 'FOOTER', 'TR', 'TABLE', 'UL', 'OL', 'LI', 'DL', 'DT', 'DD', 'FIGCAPTION']);
const SKIP = new Set(['SCRIPT', 'STYLE', 'HEAD', 'TITLE', 'META', 'TEMPLATE', 'NOSCRIPT', 'IMG', 'SVG', 'OBJECT', 'IFRAME']);

function styled(element: HTMLElement, inherited: Attrs): Attrs {
  const a: Attrs = {...inherited}, tag = element.tagName, style = element.style;
  // Inline style wins over the tag: Docs wraps content in <b style="font-weight:normal">.
  if (style.fontWeight) a.bold = style.fontWeight === 'bold' || Number(style.fontWeight) >= 600;
  else if (tag === 'B' || tag === 'STRONG' || /^H[1-6]$/.test(tag)) a.bold = true;
  if (style.fontStyle) a.italic = style.fontStyle === 'italic' || style.fontStyle === 'oblique';
  else if (tag === 'I' || tag === 'EM') a.italic = true;
  const decoration = style.textDecorationLine || style.textDecoration;
  if (decoration) a.underline = decoration.includes('underline');
  else if (tag === 'U' || tag === 'INS') a.underline = true;
  for (const key of ['bold', 'italic', 'underline'] as const) if (a[key] === false) delete a[key];
  return a;
}

export function richFromHtml(html: string): RichText {
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const chars: string[] = [], attrs: Attrs[] = [], lines: Paragraph[] = [];
  let current: Paragraph = {}, atLineStart = true;
  const newline = () => { chars.push('\n'); attrs.push({}); lines.push(current); current = {}; atLineStart = true; };
  const breakBlock = () => { if (!atLineStart) newline(); };

  function walk(node: Node, a: Attrs, lists: ('bullet' | 'number')[], pre: boolean) {
    node.childNodes.forEach(child => {
      if (child.nodeType === Node.TEXT_NODE) {
        let value = child.textContent || '';
        if (!pre) {
          value = value.replace(/\s+/g, ' ');
          if (atLineStart) value = value.replace(/^ /, '');
        }
        for (const ch of value) {
          if (ch === '\n') { newline(); continue; }
          for (let i = 0; i < ch.length; i++) { chars.push(ch[i]); attrs.push({...a}); }
          atLineStart = false;
        }
        return;
      }
      if (!(child instanceof HTMLElement) || SKIP.has(child.tagName)) return;
      const tag = child.tagName, next = styled(child, a);
      if (tag === 'BR') { newline(); return; }
      if (tag === 'UL' || tag === 'OL') { breakBlock(); walk(child, next, [...lists, tag === 'OL' ? 'number' : 'bullet'], pre); breakBlock(); return; }
      if (tag === 'LI') {
        breakBlock();
        current = {list: lists[lists.length - 1] || 'bullet', ...(lists.length > 1 ? {level: Math.min(2, lists.length - 1)} : {})};
        walk(child, next, lists, pre); breakBlock(); return;
      }
      if (BLOCK.has(tag)) { breakBlock(); walk(child, next, lists, pre || tag === 'PRE'); breakBlock(); return; }
      walk(child, next, lists, pre);
    });
  }
  walk(doc.body, {}, [], false);
  // Drop trailing blank lines and trailing spaces on each line.
  while (chars.length && chars[chars.length - 1] === '\n') { chars.pop(); attrs.pop(); current = lines.pop() || {}; }
  lines.push(current);
  let text = chars.join('');
  const keep: number[] = [];
  let offset = 0;
  text.split('\n').forEach((line, index, all) => {
    const trimmed = line.replace(/ +$/, '');
    for (let i = 0; i < trimmed.length; i++) keep.push(offset + i);
    if (index < all.length - 1) keep.push(offset + line.length);
    offset += line.length + 1;
  });
  text = keep.map(i => text[i]).join('');
  const finalAttrs = keep.map(i => attrs[i]);
  return {text, marks: marksOf(finalAttrs), paragraphs: compactParagraphs(text, lines)};
}

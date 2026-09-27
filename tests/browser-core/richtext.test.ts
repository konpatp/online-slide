import {test} from 'node:test';
import assert from 'node:assert/strict';
import {toggleMark, setMark, rangeHas, setParagraphs, splice, textEdit, lineAt} from '../../src/editor/text';

const value = (text: string) => ({text, marks: []});

test('independent attributes overlap and merge into minimal runs', () => {
  let v = toggleMark(value('hello world'), 0, 5, 'bold', false);
  v = toggleMark(v, 3, 11, 'italic', false);
  v = setMark(v, 6, 11, 'color', '#d46b32');
  assert.deepEqual(v.marks, [
    {start: 0, end: 3, bold: true}, {start: 3, end: 5, bold: true, italic: true},
    {start: 5, end: 6, italic: true}, {start: 6, end: 11, italic: true, color: '#d46b32'}]);
  assert.equal(rangeHas(v, 0, 5, 'bold', false), true);
  assert.equal(rangeHas(v, 0, 6, 'bold', false), false);
  // Clearing an attribute leaves the others intact and re-merges.
  v = setMark(v, 0, 11, 'italic', undefined);
  assert.deepEqual(v.marks, [{start: 0, end: 5, bold: true}, {start: 6, end: 11, color: '#d46b32'}]);
});

test('toggle turns on unless the whole range already has it (respecting inherited style)', () => {
  const partly = toggleMark(value('abcd'), 0, 2, 'underline', false);
  assert.deepEqual(toggleMark(partly, 0, 4, 'underline', false).marks, [{start: 0, end: 4, underline: true}]);
  assert.deepEqual(toggleMark(value('abcd'), 0, 4, 'bold', true).marks, [{start: 0, end: 4, bold: false}]);
});

test('paragraph settings follow lines and vanish when all plain', () => {
  let v = setParagraphs(value('one\ntwo\nthree'), 4, 9, p => ({...p, list: 'bullet'}));
  assert.deepEqual(v.paragraphs, [{}, {list: 'bullet'}, {list: 'bullet'}]);
  v = setParagraphs(v, 0, 0, p => ({...p, align: 'center'}));
  assert.deepEqual(v.paragraphs, [{align: 'center'}, {list: 'bullet'}, {list: 'bullet'}]);
  v = setParagraphs(v, 0, 13, () => ({}));
  assert.equal(v.paragraphs, undefined);
  assert.equal(lineAt('a\nb\nc', 4), 2);
});

test('Enter inside a list continues it; the new line keeps character styles to its left', () => {
  const list = setParagraphs(toggleMark(value('item'), 0, 4, 'bold', false), 0, 0, () => ({list: 'number'}));
  const split = splice(list, 2, 2, value('\n'));
  assert.equal(split.text, 'it\nem');
  assert.deepEqual(split.paragraphs, [{list: 'number'}, {list: 'number'}]);
  assert.deepEqual(split.marks, [{start: 0, end: 2, bold: true}, {start: 3, end: 5, bold: true}]);
});

test('plain inserts adopt the surrounding style; rich inserts bring their own', () => {
  const bold = toggleMark(value('ab'), 0, 2, 'bold', false);
  assert.deepEqual(splice(bold, 1, 1, value('XY')).marks, [{start: 0, end: 4, bold: true}]);
  const rich = {text: 'Q', marks: [{start: 0, end: 1, italic: true}]};
  assert.deepEqual(splice(value('ab'), 1, 1, rich).marks, [{start: 1, end: 2, italic: true}]);
});

test('pasted list paragraphs apply at a line start; deleting across lines merges them', () => {
  const pasted = {text: 'x\ny', marks: [], paragraphs: [{list: 'bullet' as const}, {list: 'bullet' as const}]};
  const at = splice(value('start\n'), 6, 6, pasted);
  assert.equal(at.text, 'start\nx\ny');
  assert.deepEqual(at.paragraphs, [{}, {list: 'bullet'}, {list: 'bullet'}]);
  const listed = setParagraphs(value('a\nb\nc'), 0, 5, () => ({list: 'bullet'}));
  const merged = splice(listed, 1, 4, value(''));
  assert.equal(merged.text, 'a\nc'.replace('\n', ''));
  assert.deepEqual(merged.paragraphs, [{list: 'bullet'}]);
});

test('edits carry wording, marks and paragraphs together; plain text stays plain', () => {
  assert.deepEqual(textEdit(value('plain')), {text: 'plain', marks: []});
  const v = setParagraphs(value('a\nb'), 2, 2, () => ({align: 'right'}));
  assert.deepEqual(textEdit(v), {text: 'a\nb', marks: [], paragraphs: [{}, {align: 'right'}]});
});

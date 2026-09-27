import {test} from 'node:test';
import assert from 'node:assert/strict';
import {normalize, cellsIn, rowsIn, columnsIn} from '../../src/editor/table-range';
import type {TableModel} from '../../src/editor/model';

const table: TableModel = {
  columns: [{id: 'c0', label: 'h0', width: 1}, {id: 'c1', label: 'h1', width: 1}, {id: 'c2', label: 'h2', width: 1}],
  rows: [{id: 'r0', label: 'l0', cells: ['a', 'b'], best: null, globalBest: null},
         {id: 'r1', label: 'l1', cells: ['c', 'd'], best: null, globalBest: null}],
  components: {}};

test('ranges normalize from any corner', () => {
  assert.deepEqual(normalize({tableKey: 't', row0: 1, col0: 2, row1: -1, col1: 1}), {tableKey: 't', row0: -1, row1: 1, col0: 1, col1: 2});
});
test('cells cover values, labels and headers inside the rectangle only', () => {
  assert.deepEqual(cellsIn({tableKey: 't', row0: 0, col0: 1, row1: 1, col1: 2}, table), ['a', 'b', 'c', 'd']);
  assert.deepEqual(cellsIn({tableKey: 't', row0: -1, col0: 0, row1: 0, col1: 1}, table), ['h0', 'h1', 'l0', 'a']);
});
test('structural spans skip the header row and label column', () => {
  assert.deepEqual(rowsIn({tableKey: 't', row0: -1, col0: 0, row1: 1, col1: 0}), {first: 0, last: 1});
  assert.deepEqual(columnsIn({tableKey: 't', row0: 0, col0: 0, row1: 0, col1: 2}), {first: 1, last: 2});
});

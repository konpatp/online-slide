import {test} from 'node:test';
import assert from 'node:assert/strict';
import {numericCell,heatDomain,heatColor} from '../../src/recipes/tableHeatmap';

test('heatmap reads numbers, never invents values for missing or textual cells',()=>{
  for(const value of ['', '—', 'Pending', '12 ms', 'NaN', 'Infinity']) assert.equal(numericCell(value),null);
  assert.equal(numericCell(' 12.34 '),12.34);
  assert.equal(numericCell('-1e2'),-100);
  assert.deepEqual(heatDomain([null,12,30]),[12,30]);
  assert.equal(heatDomain([null]),null);
  assert.equal(heatColor(null,[10,100]),null);
});
test('fixed-domain colors are deterministic and contrast-safe throughout the scale',()=>{
  for(let value=10;value<=100;value+=.25) assert.ok(heatColor(value,[10,100])!.contrast>=4.5);
  assert.equal(heatColor(10,[10,100])!.background,'rgb(22, 139, 128)');
  assert.equal(heatColor(55,[10,100])!.background,'rgb(242, 207, 98)');
  assert.equal(heatColor(100,[10,100])!.background,'rgb(201, 79, 53)');
  assert.deepEqual(heatColor(30,[10,100]),heatColor(numericCell('30.00'),[10,100]));
  assert.equal(heatColor(5,[10,100])!.background,heatColor(10,[10,100])!.background);
  assert.ok(heatColor(12,[12,12])!.contrast>=4.5);
});

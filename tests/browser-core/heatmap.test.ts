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
  assert.equal(heatColor(Math.sqrt(1000),[10,100])!.background,'rgb(242, 207, 98)');
  assert.equal(heatColor(100,[10,100])!.background,'rgb(201, 79, 53)');
  assert.deepEqual(heatColor(30,[10,100]),heatColor(numericCell('30.00'),[10,100]));
  assert.equal(heatColor(5,[10,100])!.background,heatColor(10,[10,100])!.background);
  assert.ok(heatColor(12,[12,12])!.contrast>=4.5);
});
test('robust log scale excludes extreme observations without changing values',()=>{
  assert.deepEqual(heatDomain([10,11,12,13,14,15,10000]),[10,15]);
  assert.deepEqual(heatDomain([.00001,10,11,12,13,14,15]),[10,15]);
  assert.deepEqual(heatDomain([10,10,10,10,10000]),[10,10]);
  assert.equal(heatColor(10000,[10,15])!.background,heatColor(15,[10,15])!.background);
  assert.equal(heatColor(10000,[10,15])!.value,10000);
  assert.equal(heatColor(10000,[10,10])!.background,heatColor(15,[10,15])!.background);
  assert.equal(heatColor(0,[10,100]),null);
  assert.deepEqual(heatDomain([null,0,-1,10,100]),[10,100]);
  assert.equal(heatDomain([0,-1,null]),null);
  assert.equal(heatColor(10,[1,100])!.background,heatColor(100,[10,1000])!.background);
  assert.equal(heatColor(55,[10,100],'linear')!.background,'rgb(242, 207, 98)');
  assert.deepEqual(heatDomain([-10,0,10],'linear'),[-10,10]);
});

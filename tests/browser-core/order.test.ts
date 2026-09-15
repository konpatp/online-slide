import {test} from 'node:test';
import assert from 'node:assert/strict';
import {moveBefore} from '../../src/editor/order';

test('relative moves preserve every identity and never mutate the source', () => {
  const order = ['a','hidden','b','created'];
  assert.deepEqual(moveBefore(order,'a',null), ['hidden','b','created','a']);
  assert.deepEqual(moveBefore(order,'created','a'), ['created','a','hidden','b']);
  assert.deepEqual(moveBefore(order,'hidden','created'), ['a','b','hidden','created']);
  assert.deepEqual(order,['a','hidden','b','created']);
});
test('missing or unchanged targets are no-ops', () => {
  for (const [id,before] of [['a','a'],['a','b'],['missing','a'],['a','missing']] as const)
    assert.deepEqual(moveBefore(['a','b'],id,before), ['a','b']);
});

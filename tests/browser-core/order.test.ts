import {test} from 'node:test';
import assert from 'node:assert/strict';
import {moveBefore, moveManyBefore} from '../../src/editor/order';

test('group move preserves deck ordering and rejects stale identities', () => {
  const order = ['a','hidden','b','c','d'];
  assert.deepEqual(moveManyBefore(order,['b','a'],null), ['hidden','c','d','a','b']);
  assert.deepEqual(moveManyBefore(order,['c','d'],'a'), ['c','d','a','hidden','b']);
  assert.deepEqual(moveManyBefore(order,['a','missing'],null), order);
  assert.deepEqual(moveManyBefore(order,['a','b'],'b'), order);
  assert.deepEqual(moveManyBefore(order,[],null), order);
});

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

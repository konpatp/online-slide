import {test} from 'node:test';
import assert from 'node:assert/strict';
import {navigationOrder,visibleDestination} from '../../src/editor/navigation';
test('presenter sequence excludes hidden identities; editor retains them',()=>{
 const order=['a','b','c','d'];
 assert.deepEqual(navigationOrder(order,['a','c'],true),['b','d']);
 assert.deepEqual(navigationOrder(order,['a','c'],false),order);
 assert.equal(visibleDestination(order,['b','d'],'a'),'b');
 assert.equal(visibleDestination(order,['b'],'d'),'b');
 assert.equal(visibleDestination(order,[],'a'),null);
});

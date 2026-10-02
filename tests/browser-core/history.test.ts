import {test} from 'node:test';
import assert from 'node:assert/strict';
import {EditHistory} from '../../src/editor/history';
import {copy} from '../../src/editor/snapshot';
import type {Snapshot} from '../../src/editor/model';
const seed=():Snapshot=>({schema:'online-slide/state@4',order:['a','b'],hidden:[],overlays:{},objects:{},tables:{},textBoxes:{}});
test('successive undo of edits, movement and deletion survives save acknowledgements',()=>{
  const h=new EditHistory();let s=seed();
  h.begin(s,'text:a:title');s.overlays={a:{title:{text:'Edited'}}};h.commit(s);
  const edited=copy(s);
  h.begin(s,'object:a:line');s.objects={a:{line:{kind:'segment',from:[0,0],to:[1,1]}}};h.commit(s);
  const moved=copy(s);
  h.begin(s);s.objects={a:{line:{kind:'segment',from:[0,0],to:[1,1],deleted:true}}};h.commit(s);
  s=h.undo(copy(s))!;assert.deepEqual(s,moved);
  s=h.undo(s)!;assert.deepEqual(s,edited);
  s=h.undo(s)!;assert.deepEqual(s,seed());assert.equal(h.available(),false);
});
test('undo keeps independent remote edits and refuses same-target overwrite',()=>{
  const h=new EditHistory();const s=seed();h.begin(s);s.overlays={a:{title:{text:'mine'}}};h.commit(s);
  s.overlays.b={title:{text:'remote'}};
  assert.deepEqual(h.undo(s)!.overlays,{b:{title:{text:'remote'}}});
  h.begin(s);s.overlays.a={title:{text:'new'}};h.commit(s);
  s.overlays.a={title:{text:'other editor'}};
  assert.throws(()=>h.undo(s),/another editor/);
  assert.equal(h.available(),true);
});
test('one drag is one history entry; pending text is committed before deletion',()=>{
  const h=new EditHistory();let s=seed();h.begin(s,'object:a:line');
  s.objects={a:{line:{kind:'segment',from:[0,0],to:[1,1]}}};
  h.begin(s,'object:a:line');s.objects={a:{line:{kind:'segment',from:[0,0],to:[2,2]}}};h.commit(s);
  s=h.undo(s)!;assert.deepEqual(s,seed());assert.equal(h.available(),false);
  h.begin(s,'text:a:title');s.overlays={a:{title:{text:'typed'}}};
  h.begin(s);s.overlays={a:{title:{text:'typed',deleted:true}}};h.commit(s);
  assert.deepEqual(h.undo(s)!.overlays,{a:{title:{text:'typed'}}});
});

test('redo re-applies undone edits in order; a new edit ends the redo line',()=>{
  const h=new EditHistory();let s=seed();
  h.begin(s,'text:a:title');s.overlays={a:{title:{text:'one'}}};h.commit(s);const one=copy(s);
  h.begin(s);s.hidden=['b'];h.commit(s);const two=copy(s);
  s=h.undo(s)!;s=h.undo(s)!;assert.deepEqual(s,seed());assert.equal(h.redoAvailable(),true);
  s=h.redo(s)!;assert.deepEqual(s,one);
  s=h.redo(s)!;assert.deepEqual(s,two);assert.equal(h.redoAvailable(),false);
  s=h.undo(s)!;assert.deepEqual(s,one);
  h.begin(s);s.order=['b','a'];h.commit(s);
  assert.equal(h.redoAvailable(),false);assert.equal(h.redo(s),null);
});
test('redo keeps independent remote edits and refuses when the target changed',()=>{
  const h=new EditHistory();let s=seed();
  h.begin(s);s.overlays={a:{title:{text:'mine'}}};h.commit(s);
  s=h.undo(s)!;
  s.overlays.b={title:{text:'remote'}};
  s=h.redo(s)!;assert.deepEqual(s.overlays,{a:{title:{text:'mine'}},b:{title:{text:'remote'}}});
  s=h.undo(s)!;s.overlays.a={title:{text:'other editor'}};
  assert.throws(()=>h.redo(s),/changed since the undo/);
  assert.equal(h.redoAvailable(),true);
});

test('a source change on one slide drops only the steps that edited it',()=>{
  const h=new EditHistory();let s=seed();
  h.begin(s);s.overlays={a:{title:{text:'on a'}}};h.commit(s);
  h.begin(s);s.overlays={...s.overlays,b:{title:{text:'on b'}}};h.commit(s);
  h.begin(s);s.hidden=['b'];h.commit(s);
  h.dropTouching(['a']);
  s=h.undo(s)!;assert.deepEqual(s.hidden,[]);
  s=h.undo(s)!;assert.equal(s.overlays.b,undefined);assert.deepEqual(s.overlays.a,{title:{text:'on a'}});
  assert.equal(h.available(),false);
});

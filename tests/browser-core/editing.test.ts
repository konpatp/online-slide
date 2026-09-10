import {test} from 'node:test';
import assert from 'node:assert/strict';
import {copy, snapshot, carryForward, saveRequest} from '../../src/editor/snapshot';
import {textEdit, toggleBold} from '../../src/editor/text';
import {SaveQueue} from '../../src/editor/save-queue';
import type {SaveResponse} from '../../src/editor/save-queue';
import type {RevisionedSnapshot, SaveRequest, TextOverlay} from '../../src/editor/model';

function state(): RevisionedSnapshot {
  return {schema:'online-slide/state@4',revision:1,sourceRevision:'source',slideRevisions:{a:'1',b:'2'},
    order:['a','b'],hidden:[],overlays:{},objects:{},tables:{},textBoxes:{}};
}
test('marks cannot be authored without their exact text', () => {
  // Compile-time negative regression. Removing the contract makes tsc fail.
  // @ts-expect-error marks without wording are not a valid edit
  const invalid: TextOverlay = {marks:[{start:0,end:1,bold:true}]};
  assert.ok(invalid);
  assert.deepEqual(textEdit({text:'same source',marks:[{start:0,end:4,bold:true}]}),
    {text:'same source',marks:[{start:0,end:4,bold:true}]});
});
test('range toggle preserves multiline UTF-16 offsets and inherited bold', () => {
  const value = {text:'x\n😀 word',marks:[]};
  const edited = toggleBold(value,5,9,false);
  assert.deepEqual(edited.marks,[{start:5,end:9,bold:true}]);
  assert.deepEqual(toggleBold(edited,5,9,false).marks,[{start:5,end:9,bold:false}]);
  assert.deepEqual(toggleBold({text:'best',marks:[]},0,4,true).marks,[{start:0,end:4,bold:false}]);
});
test('pending order, visibility, formatting and removals merge without erasing remote edits', () => {
  const base=state(),local=copy(base),remote=copy(base);
  base.overlays={a:{title:{text:'old',marks:[],color:'#000000'}}};
  local.overlays={a:{title:{text:'new',marks:[{start:0,end:3,bold:true}]}}};
  remote.overlays={a:{title:{text:'old',marks:[],color:'#000000',fontScale:1.2}},b:{title:{text:'remote'}}};
  local.order=['b','a'];local.hidden=['a'];remote.order=['a','added','b'];
  const merged=carryForward(base,local,remote);
  assert.deepEqual(merged.order,['b','added','a']);
  assert.deepEqual(merged.hidden,['a']);
  assert.deepEqual(merged.overlays,{a:{title:{text:'new',marks:[{start:0,end:3,bold:true}],fontScale:1.2}},b:{title:{text:'remote'}}});
  assert.deepEqual(remote.order,['a','added','b']);
});
test('snapshot excludes sources and request binds both revisions', () => {
  const value={...state(),slides:{private:'content'}};
  assert.equal('slides' in snapshot(value),false);
  const request=saveRequest(value,snapshot(value));
  assert.equal(request.baseRevision,1);assert.equal(request.baseSourceRevision,'source');
  assert.deepEqual(request.baseSlideRevisions,{a:'1',b:'2'});
});

function fixture() {
  let current=state(),accepted=copy(current),stale=false;
  const calls: {body:SaveRequest;resolve:(result:SaveResponse)=>void;reject:(error:Error)=>void}[]=[];
  const events:string[]=[],timers:(()=>void)[]=[];
  const queue=new SaveQueue<RevisionedSnapshot>({
    current:()=>current,accepted:()=>accepted,decode:value=>value as RevisionedSnapshot,stale:()=>stale,
    request:body=>new Promise((resolve,reject)=>calls.push({body,resolve,reject})),
    acceptedResult:(remote,next,clean)=>{accepted=remote;current=next;events.push(clean?'clean':'pending');},
    conflict:(remote)=>{accepted=remote;current=copy(remote);events.push('conflict');},
    invalid:()=>events.push('invalid'),retry:()=>events.push('retry'),
    runtimeChanged:()=>events.push('stale'),schedule:fn=>timers.push(fn)
  });
  return {queue,calls,events,timers,get current(){return current;},setStale(){stale=true;}};
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
test('one request at a time; edits during a delayed ACK become the next save',async()=>{
  const f=fixture();f.current.overlays={a:{title:{text:'first'}}};f.queue.enqueue();
  f.current.overlays={a:{title:{text:'second'}}};f.queue.enqueue();
  assert.equal(f.calls.length,1);
  f.calls[0].resolve({ok:true,status:200,payload:{...state(),...f.calls[0].body.snapshot,revision:2}});
  await settle();assert.equal(f.calls.length,2);
  assert.equal(f.calls[1].body.baseRevision,2);
  assert.deepEqual(f.calls[1].body.snapshot.overlays,{a:{title:{text:'second'}}});
  f.calls[1].resolve({ok:true,status:200,payload:{...state(),...f.calls[1].body.snapshot,revision:3}});
  await settle();assert.deepEqual(f.events,['pending','clean']);assert.equal(f.queue.pending,null);
});
test('typing before debounce is also carried across an ACK',async()=>{
  const f=fixture();f.queue.enqueue();f.current.overlays={a:{title:{text:'not queued yet'}}};
  f.calls[0].resolve({ok:true,status:200,payload:state()});await settle();
  assert.equal(f.calls.length,2);
  assert.deepEqual(f.calls[1].body.snapshot.overlays,f.current.overlays);
});
for(const status of [400,409,503])test(`save ${status} transition is explicit`,async()=>{
  const f=fixture();f.queue.enqueue();
  f.calls[0].resolve({ok:false,status,payload:{state:state(),error:'refused'}});await settle();
  assert.deepEqual(f.events,[status===400?'invalid':status===409?'conflict':'retry']);
  assert.equal(f.timers.length,status===503?1:0);
  assert.equal(f.queue.inFlight,null);
});
test('network retry retains latest pending intent; stale runtime stops writing',async()=>{
  const f=fixture();f.queue.enqueue();f.current.hidden=['b'];f.queue.enqueue();
  f.calls[0].reject(new Error('offline'));await settle();f.timers[0]();
  assert.deepEqual(f.calls[1].body.snapshot.hidden,['b']);
  f.setStale();f.calls[1].reject(new Error('runtime changed'));await settle();
  assert.equal(f.events[f.events.length-1],'stale');f.queue.flush();assert.equal(f.calls.length,2);
});

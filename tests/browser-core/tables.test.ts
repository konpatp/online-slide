import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createTableEditor} from '../../src/editor/tables';
import type {TableSlide,Cell} from '../../src/editor/tables';
import type {TableModel} from '../../src/editor/model';

test('semantic table commands retain cell identity through row/column movement',()=>{
  const slide:TableSlide={id:'sample',recipe:'evidence-table',data:{columns:['name','a','b'],
    rows:[{label:'first',cells:['first-a','first-b'],best:1},{label:'second',cells:['second-a','second-b']}]}};
  const state={slides:{sample:slide},tables:{} as Record<string,TableModel>};
  let selected:{slideId:string;componentId?:string;tableCell?:Cell}|null=null;
  let saves=0;
  const editor=createTableEditor({getState:()=>state,getSelected:()=>selected,clearSelection:()=>{selected=null;},
    isEditMode:()=>true,stage:{} as HTMLElement,beginChange(){},render(){},persist(){saves++;},
    effectiveComponent:()=>({kind:'text',text:''}),updateOverlay(){}});
  selected={slideId:slide.id,componentId:'first-b',tableCell:editor.tableCell(slide,'first-b')!};
  editor.mutateSelectedTable('column-left');
  assert.deepEqual(editor.effectiveTable(slide).rows[0].cells,['first-b','first-a']);
  assert.equal(editor.effectiveTable(slide).rows[0].best,'first-b');
  selected.tableCell=editor.tableCell(slide,'first-b')!;
  editor.mutateSelectedTable('row-down');
  assert.equal(editor.tableCell(slide,'first-b')?.rowIndex,1);
  editor.mutateSelectedTable('table-reset');
  assert.equal(selected,null);assert.deepEqual(state.tables,{});assert.equal(saves,3);
});

test('multiple tables keep their own semantic conflict domains',()=>{
  const data={columns:['name','a'],rows:[{label:'row',cells:['value']}]};
  const slide:TableSlide={id:'sample',recipe:'evidence-table',data:{...data,tables:[{...data,id:'one'},
    {id:'two',columns:['other-name','other-a'],rows:[{label:'other-row',cells:['other-value']}]}]}};
  const state={slides:{sample:slide},tables:{} as Record<string,TableModel>};
  const editor=createTableEditor({getState:()=>state,getSelected:()=>null,clearSelection(){},
    isEditMode:()=>true,stage:{} as HTMLElement,beginChange(){},render(){},persist(){},
    effectiveComponent:()=>({kind:'text',text:''}),updateOverlay(){}});
  const contexts=editor.tableContexts(slide);
  assert.equal(editor.tableCell(slide,'other-value')?.tableKey,'sample::table::two');
  editor.ensureTable(contexts[1]);
  assert.deepEqual(Object.keys(state.tables),['sample::table::two']);
});

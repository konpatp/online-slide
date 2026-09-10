import type {TextComponent, TextMark, TableModel} from './model';
export interface TableData {
  id?: string; tables?: TableData[];
  columns: string[]; columnWeights?: number[];
  rows: {label:string; cells:string[]; best?:number; globalBest?:number}[];
}
export interface TableSlide {id:string; recipe:string; data:TableData; _tableKey?:string}
export interface Cell {tableKey:string; header:boolean; rowIndex:number; columnIndex:number; rowId:string; columnId:string}
interface TableSelection {slideId:string; componentId?:string; tableCell?:Cell}
interface TableHost {
  getState(): {slides:Record<string,TableSlide>; tables:Record<string,TableModel>};
  getSelected(): TableSelection | null;
  clearSelection(): void;
  isEditMode(): boolean;
  stage: HTMLElement;
  beginChange(): void; render(): void; persist(): void;
  effectiveComponent(slide:TableSlide, id:string): TextComponent;
  updateOverlay(slide:string, id:string, key:'text'|'marks', value:string|TextMark[]): void;
}
interface ColumnGesture {slide:TableSlide; table:TableModel; index:number; startX:number; startWidth:number; bodyWidth:number; total:number}
/** Native semantic tables: structural commands, paste and column gestures. */
export function createTableEditor({getState,getSelected,clearSelection,isEditMode,stage,beginChange,render,persist,effectiveComponent,updateOverlay}: TableHost) {
let tableColumnGesture: ColumnGesture | null = null;
function tableContexts(slide: TableSlide): TableSlide[] {
  if(slide._tableKey || !slide.data.tables) return [slide];
  return slide.data.tables.map(function(data) {
    return Object.assign({},slide,{data:data,_tableKey:slide.id+'::table::'+data.id});
  });
}

function selectedTableContext(slide: TableSlide, cell: Cell) {
  return tableContexts(slide).find(function(item) {return (item._tableKey || item.id)===cell.tableKey;}) || slide;
}

function sourceTableModel(slide: TableSlide): TableModel {
  if(slide.data.tables) throw new Error('Select a semantic table before changing its structure');
  return {
    columns: slide.data.columns.map(function (componentId, index) {
      return {id: componentId, label: componentId,
        width: (slide.data.columnWeights || [])[index] || (index === 0 ? 1.5 : 1)};
    }),
    rows: slide.data.rows.map(function (row) {
      return {
        id: row.label,
        label: row.label,
        cells: row.cells.slice(),
        best: typeof row.best === 'number' && Number.isInteger(row.best) ? row.cells[row.best] : null,
        globalBest: typeof row.globalBest === 'number' && Number.isInteger(row.globalBest) ? row.cells[row.globalBest] : null
      };
    }),
    components: {}
  };
}

function effectiveTable(slide: TableSlide) {
  return (getState().tables || {})[slide._tableKey || slide.id] || sourceTableModel(slide);
}

function ensureTable(slide: TableSlide) {
  if (!getState().tables) getState().tables = {};
  var key=slide._tableKey || slide.id;
  if (!getState().tables[key]) getState().tables[key] = sourceTableModel(slide);
  return getState().tables[key];
}

function tableToken() {
  var random = Math.random().toString(36).slice(2, 8);
  return Date.now().toString(36) + "-" + random;
}

function insertedTableText(table: TableModel, prefix: string, value: string, role: string) {
  var id = prefix + "-" + tableToken();
  table.components[id] = {kind: "text", text: value, role: role};
  return id;
}

function retireTableComponent(table: TableModel, componentId: string) {
  if (table.components[componentId]) delete table.components[componentId];
}

function tableCell(slide: TableSlide | null, componentId: string): Cell | null {
  if (!slide || slide.recipe !== "evidence-table") return null;
  if(slide.data.tables) {
    var found=tableContexts(slide).map(function(context) {return tableCell(context,componentId);}).filter(Boolean);
    if(found.length>1) throw new Error('Ambiguous table cell '+componentId);
    return found[0] || null;
  }
  var table = effectiveTable(slide);
  for (var columnIndex = 0; columnIndex < table.columns.length; columnIndex += 1) {
    if (table.columns[columnIndex].label === componentId) {
      return {tableKey:slide._tableKey || slide.id,header: true, rowIndex: -1, columnIndex: columnIndex,
        rowId: "table-header", columnId: table.columns[columnIndex].id};
    }
  }
  for (var rowIndex = 0; rowIndex < table.rows.length; rowIndex += 1) {
    var row = table.rows[rowIndex];
    if (row.label === componentId) {
      return {tableKey:slide._tableKey || slide.id,header: false, rowIndex: rowIndex, columnIndex: 0,
        rowId: row.id, columnId: table.columns[0].id};
    }
    var cellIndex = row.cells.indexOf(componentId);
    if (cellIndex >= 0) {
      return {tableKey:slide._tableKey || slide.id,header: false, rowIndex: rowIndex, columnIndex: cellIndex + 1,
        rowId: row.id, columnId: table.columns[cellIndex + 1].id};
    }
  }
  return null;
}

function addTableRow(slide: TableSlide, afterIndex: number) {
  var table = ensureTable(slide);
  var token = tableToken();
  var label = "table-row-" + token;
  table.components[label] = {kind: "text", text: "New row", role: "table-row-label"};
  var cells = table.columns.slice(1).map(function () {
    return insertedTableText(table, "table-cell", "—", "table-value");
  });
  var row = {id: label, label: label, cells: cells, best: null, globalBest: null};
  table.rows.splice(Math.max(0, Math.min(table.rows.length, afterIndex + 1)), 0, row);
  return row;
}

function addTableColumn(slide: TableSlide, afterIndex: number) {
  var table = ensureTable(slide);
  var label = insertedTableText(table, "table-column", "New column", "table-heading");
  var insertAt = Math.max(1, Math.min(table.columns.length, afterIndex + 1));
  table.columns.splice(insertAt, 0, {id: label, label: label, width: 1});
  table.rows.forEach(function (row) {
    row.cells.splice(insertAt - 1, 0,
      insertedTableText(table, "table-cell", "—", "table-value"));
  });
  return insertAt;
}

function mutateSelectedTable(action: string) {
  const selection = getSelected();
  if (!selection?.tableCell) return;
  var slide = getState().slides[selection.slideId];
  if (!slide || slide.recipe !== "evidence-table") return;
  slide=selectedTableContext(slide,selection.tableCell);
  var table = ensureTable(slide);
  var cell = selection.tableCell;
  beginChange();
  if (action === "table-reset") {
    delete getState().tables[slide._tableKey || slide.id];
    clearSelection();
  } else if (action === "row-add") {
    var row = addTableRow(slide, cell.rowIndex < 0 ? table.rows.length - 1 : cell.rowIndex);
    selection.componentId = row.label;
  } else if (action === "row-delete" && cell.rowIndex >= 0 && table.rows.length > 1) {
    var removedRow = table.rows.splice(cell.rowIndex, 1)[0];
    retireTableComponent(table, removedRow.label);
    removedRow.cells.forEach(function (componentId) {
      retireTableComponent(table, componentId);
    });
    clearSelection();
  } else if ((action === "row-up" || action === "row-down") && cell.rowIndex >= 0) {
    var rowTarget = cell.rowIndex + (action === "row-up" ? -1 : 1);
    if (rowTarget >= 0 && rowTarget < table.rows.length) {
      table.rows.splice(rowTarget, 0, table.rows.splice(cell.rowIndex, 1)[0]);
    }
  } else if (action === "column-add") {
    var columnIndex = addTableColumn(slide, cell.columnIndex);
    selection.componentId = table.columns[columnIndex].label;
  } else if (action === "column-delete" && cell.columnIndex > 0 && table.columns.length > 2) {
    var removed = table.columns.splice(cell.columnIndex, 1)[0];
    table.rows.forEach(function (rowItem) {
      var removedCell = rowItem.cells.splice(cell.columnIndex - 1, 1)[0];
      if (rowItem.best === removedCell) rowItem.best = null;
      if (rowItem.globalBest === removedCell) rowItem.globalBest = null;
      retireTableComponent(table, removedCell);
    });
    retireTableComponent(table, removed.label);
    clearSelection();
  } else if ((action === "column-left" || action === "column-right") && cell.columnIndex > 0) {
    var columnTarget = cell.columnIndex + (action === "column-left" ? -1 : 1);
    if (columnTarget > 0 && columnTarget < table.columns.length) {
      table.columns.splice(columnTarget, 0, table.columns.splice(cell.columnIndex, 1)[0]);
      table.rows.forEach(function (rowItem) {
        rowItem.cells.splice(columnTarget - 1, 0,
          rowItem.cells.splice(cell.columnIndex - 1, 1)[0]);
      });
    }
  }
  render();
  persist();
}

function setTableText(slide: TableSlide, table: TableModel, componentId: string, value: string) {
  updateOverlay(slide.id, componentId, "text", value);
  // TSV replacement must not retain ranges over unrelated characters.
  if (effectiveComponent(getState().slides[slide.id],componentId).marks)
    updateOverlay(slide.id,componentId,'marks',[]);
}

function pasteTableGrid(slide: TableSlide, componentId: string, raw: string) {
  const start = tableCell(slide, componentId);
  if (!start) return false;
  slide=selectedTableContext(slide,start);
  var values = raw.replace(/\r/g, "").split("\n").filter(function (line, index, rows) {
    return line.length || index < rows.length - 1;
  }).map(function (line) { return line.split("\t"); });
  if (!values.length || (values.length === 1 && values[0].length === 1)) return false;
  var table = ensureTable(slide);
  beginChange();
  while (start.columnIndex + Math.max.apply(null, values.map(function (row) { return row.length; })) > table.columns.length) {
    addTableColumn(slide, table.columns.length - 1);
  }
  if (!start.header) {
    while (start.rowIndex + values.length > table.rows.length) addTableRow(slide, table.rows.length - 1);
  }
  values.forEach(function (valuesRow, rowOffset) {
    valuesRow.forEach(function (value, columnOffset) {
      var columnIndex = start.columnIndex + columnOffset;
      var targetId;
      if (start.header && rowOffset === 0) {
        targetId = table.columns[columnIndex].label;
      } else {
        var rowIndex = start.header ? rowOffset - 1 : start.rowIndex + rowOffset;
        if (rowIndex < 0) return;
        targetId = columnIndex === 0 ? table.rows[rowIndex].label : table.rows[rowIndex].cells[columnIndex - 1];
      }
      setTableText(slide, table, targetId, value.trim());
    });
  });
  render();
  persist();
  return true;
}

function startTableColumnResize(slide: TableSlide, columnId: string, event: PointerEvent) {
  if (!isEditMode()) return;
  event.preventDefault();
  event.stopPropagation();
  var table = ensureTable(slide);
  var index = table.columns.findIndex(function (column) { return column.id === columnId; });
  if (index < 0) return;
  beginChange();
  var body = (event.target as HTMLElement).closest<HTMLElement>(".table-body")!.getBoundingClientRect();
  tableColumnGesture = {
    slide: slide,
    table: table,
    index: index,
    startX: event.clientX,
    startWidth: table.columns[index].width,
    bodyWidth: body.width,
    total: table.columns.reduce(function (sum, column) { return sum + column.width; }, 0)
  };
  document.body.classList.add("resizing-table-column");
  document.addEventListener("pointermove", moveTableColumnResize);
  document.addEventListener("pointerup", finishTableColumnResize, {once: true});
  document.addEventListener("pointercancel", finishTableColumnResize, {once: true});
}

function moveTableColumnResize(event: PointerEvent) {
  if (!tableColumnGesture) return;
  event.preventDefault();
  var gesture = tableColumnGesture;
  var delta = (event.clientX - gesture.startX) / gesture.bodyWidth * gesture.total;
  gesture.table.columns[gesture.index].width = Math.max(.35, Math.min(4, gesture.startWidth + delta));
  const tableElement = stage.querySelector(".evidence-table");
  if (!tableElement) return;
  var total = gesture.table.columns.reduce(function (sum, column) { return sum + column.width; }, 0);
  gesture.table.columns.forEach(function (column) {
    var col = tableElement.querySelector<HTMLElement>('col[data-table-column-id="' + column.id + '"]');
    if (col) col.style.width = (column.width / total * 100).toFixed(3) + "%";
  });
}

function finishTableColumnResize() {
  document.removeEventListener("pointermove", moveTableColumnResize);
  document.removeEventListener("pointerup", finishTableColumnResize);
  document.removeEventListener("pointercancel", finishTableColumnResize);
  document.body.classList.remove("resizing-table-column");
  if (!tableColumnGesture) return;
  tableColumnGesture = null;
  render();
  persist();
}


return {tableContexts,selectedTableContext,sourceTableModel,effectiveTable,ensureTable,tableCell,mutateSelectedTable,pasteTableGrid,startTableColumnResize};
}

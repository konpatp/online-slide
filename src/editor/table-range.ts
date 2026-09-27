/** Rectangular cell ranges in native tables.
 *
 * A range lives in grid coordinates of one table: row -1 is the header row
 * and column 0 the row-label column. Dragging from one cell into another, or
 * Shift-clicking from the selected cell, selects the rectangle between them;
 * row, column and whole-table selection come from the table toolbar. Starting
 * a drag inside one cell still selects its text as usual; only crossing into
 * another cell turns the gesture into a range.
 */
import type {TableModel} from './model';

export interface CellRange { tableKey: string; row0: number; col0: number; row1: number; col1: number }
export interface GridCell { tableKey: string; row: number; col: number }

export function normalize(range: CellRange): CellRange {
  return {tableKey: range.tableKey, row0: Math.min(range.row0, range.row1), row1: Math.max(range.row0, range.row1),
    col0: Math.min(range.col0, range.col1), col1: Math.max(range.col0, range.col1)};
}
/** Component ids of every cell in the range, header and labels included. */
export function cellsIn(range: CellRange, table: TableModel): string[] {
  const r = normalize(range), ids: string[] = [];
  for (let row = r.row0; row <= r.row1; row++) for (let col = r.col0; col <= r.col1; col++) {
    const id = row < 0 ? table.columns[col]?.label : col === 0 ? table.rows[row]?.label : table.rows[row]?.cells[col - 1];
    if (id) ids.push(id);
  }
  return ids;
}
export const rowsIn = (range: CellRange) => { const r = normalize(range); return {first: Math.max(0, r.row0), last: r.row1}; };
export const columnsIn = (range: CellRange) => { const r = normalize(range); return {first: Math.max(1, r.col0), last: r.col1}; };

interface RangeHost {
  stage: HTMLElement;
  isEditMode(): boolean;
  /** The single selected cell, the anchor for Shift-click. */
  anchor(): GridCell | null;
  table(tableKey: string): TableModel | null;
  /** Make a cell the editor's selected cell (the range's anchor). */
  selectCell(cell: HTMLElement): void;
  changed(): void;
}

function gridCell(node: Element | null): (GridCell & {element: HTMLElement}) | null {
  const cell = node?.closest<HTMLElement>('[data-table-cell]');
  const table = cell?.closest<HTMLElement>('[data-native-table]');
  if (!cell || !table) return null;
  return {tableKey: table.dataset.nativeTable!, row: Number(cell.dataset.tableRowIndex), col: Number(cell.dataset.tableColumnIndex), element: cell};
}

export function createTableRange(host: RangeHost) {
  let range: CellRange | null = null;

  function set(next: CellRange | null) {
    range = next && host.table(next.tableKey) ? normalize(next) : null;
    paint(); host.changed();
  }
  /** A range of one cell is just the ordinary selection. */
  const active = () => Boolean(range && (range.row0 !== range.row1 || range.col0 !== range.col1));

  function paint() {
    host.stage.querySelectorAll('.table-range-cell').forEach(node => node.classList.remove('table-range-cell'));
    if (!range || !active()) return;
    const table = host.stage.querySelector<HTMLElement>(`[data-native-table="${CSS.escape(range.tableKey)}"]`);
    table?.querySelectorAll<HTMLElement>('[data-table-cell]').forEach(cell => {
      const row = Number(cell.dataset.tableRowIndex), col = Number(cell.dataset.tableColumnIndex);
      if (row >= range!.row0 && row <= range!.row1 && col >= range!.col0 && col <= range!.col1) cell.classList.add('table-range-cell');
    });
  }

  function endTextSelection() {
    getSelection()?.removeAllRanges();
    (document.activeElement as HTMLElement | null)?.blur?.();
    host.stage.tabIndex = -1; host.stage.focus({preventScroll: true});
  }

  host.stage.addEventListener('pointerdown', event => {
    if (!host.isEditMode() || event.button !== 0) return;
    const start = gridCell(event.target as Element);
    if (!start) { if (range) set(null); return; }
    if ((event.target as Element).closest('button, .table-column-resizer')) return;
    const anchor = host.anchor();
    if (event.shiftKey && anchor && anchor.tableKey === start.tableKey) {
      event.preventDefault(); event.stopPropagation(); endTextSelection();
      set({tableKey: start.tableKey, row0: anchor.row, col0: anchor.col, row1: start.row, col1: start.col});
      return;
    }
    if (range) set(null);
    let spanning = false;
    const move = (next: PointerEvent) => {
      const over = gridCell(document.elementFromPoint(next.clientX, next.clientY));
      if (!over || over.tableKey !== start.tableKey) return;
      if (!spanning && over.row === start.row && over.col === start.col) return;
      if (!spanning) {
        spanning = true; host.selectCell(start.element); endTextSelection();
        document.body.classList.add('selecting-table-range');
      }
      next.preventDefault();
      getSelection()?.removeAllRanges();
      set({tableKey: start.tableKey, row0: start.row, col0: start.col, row1: over.row, col1: over.col});
    };
    const end = () => {
      document.removeEventListener('pointermove', move);
      document.removeEventListener('pointerup', end);
      document.removeEventListener('pointercancel', end);
      document.body.classList.remove('selecting-table-range');
      if (spanning) {
        // The click that ends a range drag is not a click into a cell.
        const swallow = (click: Event) => { click.stopPropagation(); click.preventDefault(); };
        window.addEventListener('click', swallow, {capture: true, once: true});
        setTimeout(() => window.removeEventListener('click', swallow, {capture: true}), 0);
      }
    };
    document.addEventListener('pointermove', move);
    document.addEventListener('pointerup', end);
    document.addEventListener('pointercancel', end);
  }, true);

  /** Whole row, column or table around the selected cell. */
  function selectAround(kind: 'row' | 'column' | 'table') {
    const anchor = host.anchor(), table = anchor && host.table(anchor.tableKey);
    if (!anchor || !table) return false;
    const lastRow = table.rows.length - 1, lastCol = table.columns.length - 1;
    endTextSelection();
    if (kind === 'row') set({tableKey: anchor.tableKey, row0: anchor.row, row1: anchor.row, col0: 0, col1: lastCol});
    else if (kind === 'column') set({tableKey: anchor.tableKey, row0: -1, row1: lastRow, col0: anchor.col, col1: anchor.col});
    else set({tableKey: anchor.tableKey, row0: -1, row1: lastRow, col0: 0, col1: lastCol});
    return true;
  }

  return {
    set, paint, selectAround, clear: () => { if (range) set(null); },
    active,
    range: () => (active() ? range : null),
    cells: () => {
      if (!range || !active()) return [];
      const table = host.table(range.tableKey);
      return table ? cellsIn(range, table) : [];
    }
  };
}
export type TableRange = ReturnType<typeof createTableRange>;

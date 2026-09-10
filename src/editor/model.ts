/** Browser edit contract. Python remains the authority for untrusted input.
 * Source content stays JSON; neither DOM positions nor framework state persist.
 */
export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
export type JsonMap = { [key: string]: Json };
export interface TextMark { start: number; end: number; bold: boolean }
export interface RichText { text: string; marks: TextMark[] }
export interface Region { x: number; y: number; width: number; height: number }
export interface TextStyle { color?: string; fontScale?: number; hidden?: boolean; region?: Region }
// Marks are offsets into THIS text, never an independent property command.
export type TextOverlay = TextStyle & ({ text: string; marks?: TextMark[] } | { text?: never; marks?: never });
export interface TextBox extends TextStyle { text: string; marks?: TextMark[]; region: Region }
export interface TableColumn { id: string; label: string; width: number }
export interface TableRow { id: string; label: string; cells: string[]; best: string | null; globalBest: string | null }
export interface TextComponent extends TextStyle { kind: 'text'; text: string; role?: string; marks?: TextMark[]; render?: 'latex'; display?: 'block' }
export interface TableModel { columns: TableColumn[]; rows: TableRow[]; components: Record<string, TextComponent> }
/** Mutable transport maps are deliberately opaque outside their owner.
 * Recipe-specific validation remains at the existing server boundary.
 */
export interface Snapshot {
  schema: string;
  order: string[];
  hidden: string[];
  overlays: JsonMap;
  tables: JsonMap;
  textBoxes: JsonMap;
  objects: JsonMap;
}
export interface RevisionedSnapshot extends Snapshot {
  revision: number;
  sourceRevision: string;
  slideRevisions: Record<string, string>;
}
export interface SaveRequest {
  baseRevision: number;
  baseSourceRevision: string;
  baseSlideRevisions: Record<string, string>;
  baseSnapshot: Snapshot;
  snapshot: Snapshot;
  compact: true;
}

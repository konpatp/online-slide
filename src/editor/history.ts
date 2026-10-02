import type {Snapshot} from './model';
import {snapshot, sameSnapshot, carryForward, canonical} from './snapshot';

interface Entry {before: Snapshot; after: Snapshot; group?: string; time: number}
/** Session-local undo and redo, independent of save ACKs. Store only
 * authoring state. Undo and redo replay semantic deltas over the current
 * state, never a stale full-deck snapshot, and refuse when another editor has
 * since changed the same values.
 */
export class EditHistory {
  private entries: Entry[] = [];
  private redone: Entry[] = [];
  private pending: {before: Snapshot; group?: string} | null = null;
  constructor(private limit = 100) {}
  begin(state: Snapshot, group?: string): void {
    if (this.pending && group && this.pending.group === group) return;
    this.commit(state);
    this.pending = {before: snapshot(state), group};
  }
  commit(state: Snapshot): void {
    if (!this.pending) return;
    const {before, group} = this.pending;
    this.pending = null;
    if (sameSnapshot(before, state)) return;
    const last = this.entries[this.entries.length-1], time = Date.now();
    // Only adjacent typing and arrow-key bursts coalesce; drags and deletes remain distinct.
    if ((group?.startsWith('text:') || group?.endsWith(':nudge')) && last?.group === group && time-last.time < 750 && sameSnapshot(last.after,before)) {
      last.after = snapshot(state); last.time = time;
    } else this.entries.push({before, after:snapshot(state), group, time});
    if (this.entries.length > this.limit) this.entries.shift();
    // A new change ends the redo line, as in every editor.
    this.redone = [];
  }
  available(): boolean {return Boolean(this.pending || this.entries.length);}
  redoAvailable(): boolean {return !this.pending && this.redone.length > 0;}
  clear(): void {this.entries=[];this.redone=[];this.pending=null;}
  /** Forget only steps that edited slides whose source just changed (an agent
   * republished them); every other step stays undoable. */
  dropTouching(slideIds: string[]): void {
    const touched = new Set(slideIds);
    const touches = (entry: Entry) => [...touched].some(id => (['overlays', 'objects', 'textBoxes'] as const)
      .some(field => canonical(entry.before[field]?.[id]) !== canonical(entry.after[field]?.[id])) ||
      Object.keys({...entry.before.tables, ...entry.after.tables}).some(key => (key === id || key.startsWith(id + '::table::')) &&
        canonical(entry.before.tables?.[key]) !== canonical(entry.after.tables?.[key])));
    this.entries = this.entries.filter(entry => !touches(entry));
    this.redone = this.redone.filter(entry => !touches(entry));
  }
  undo<T extends Snapshot>(current: T): T | null {
    this.commit(current);
    const entry = this.entries[this.entries.length-1];
    if (!entry) return null;
    if (!sameSnapshot(carryForward(entry.before,entry.after,current),current))
      throw new Error('Cannot undo: this object changed in another editor. Your current edits were kept.');
    const next=carryForward(entry.after,entry.before,current);
    this.entries.pop();
    this.redone.push({...entry, group: undefined});
    const previous=this.entries[this.entries.length-1];
    if(previous) previous.group=undefined;
    return next;
  }
  redo<T extends Snapshot>(current: T): T | null {
    this.commit(current);
    const entry = this.redone[this.redone.length-1];
    if (!entry) return null;
    if (!sameSnapshot(carryForward(entry.after,entry.before,current),current))
      throw new Error('Cannot redo: this object changed since the undo. Your current edits were kept.');
    const next=carryForward(entry.before,entry.after,current);
    this.redone.pop();
    this.entries.push({...entry, time: Date.now()});
    return next;
  }
}

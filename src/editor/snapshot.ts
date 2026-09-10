import type { Json, JsonMap, Snapshot, RevisionedSnapshot, SaveRequest } from './model';

export function copy<T>(value: T): T { return JSON.parse(JSON.stringify(value)); }
export function snapshot(value: Snapshot): Snapshot {
  return {schema: value.schema, order: value.order.slice(), hidden: value.hidden.slice(),
    overlays: copy(value.overlays), tables: copy(value.tables || {}),
    textBoxes: copy(value.textBoxes || {}), objects: copy(value.objects || {})};
}
export function sameSnapshot(a: Snapshot, b: Snapshot): boolean {
  return JSON.stringify(snapshot(a)) === JSON.stringify(snapshot(b));
}
const changed = (a: unknown, b: unknown) => JSON.stringify(a) !== JSON.stringify(b);
function asMap(value: Json | undefined): JsonMap {
  if (value === undefined) return {};
  if (value === null || typeof value !== 'object' || Array.isArray(value))
    throw new Error('Expected a semantic edit map');
  return value;
}
function textGroup(value: JsonMap): JsonMap {
  const result: JsonMap = {};
  for (const key of ['text', 'marks']) if (value[key] !== undefined) result[key] = value[key];
  return result;
}
function merge(a: JsonMap, b: JsonMap, c: JsonMap, depth: number): JsonMap {
  const out = copy(c);
  let keys = Object.keys({...a, ...b});
  if (depth === 1 && [a,b,c].some(value => value.marks !== undefined)) {
    if (changed(textGroup(a),textGroup(b))) {
      delete out.text; delete out.marks; Object.assign(out,textGroup(b));
    }
    keys = keys.filter(key => key !== 'text' && key !== 'marks');
  }
  for (const key of keys) {
    if (!changed(a[key], b[key])) continue;
    if (depth > 1) {
      const next = merge(asMap(a[key]), asMap(b[key]), asMap(out[key]), depth - 1);
      if (Object.keys(next).length) out[key] = next;
      else delete out[key];
    } else if (b[key] === undefined) delete out[key];
    else out[key] = copy(b[key]);
  }
  return out;
}
/** Replay only edits after the request began, never a whole stale snapshot. */
export function carryForward<T extends Snapshot>(base: Snapshot, local: Snapshot, remote: T): T {
  const result = copy(remote);
  if (changed(base.order, local.order)) {
    const known = new Set(base.order), remaining = local.order.slice();
    result.order = remote.order.map(key => {
      if (!known.has(key)) return key;
      const next = remaining.shift();
      if (next === undefined) throw new Error('Local slide order lost an identity');
      return next;
    });
  }
  const hidden = new Set(remote.hidden);
  for (const key of base.order) if (base.hidden.includes(key) !== local.hidden.includes(key)) {
    if (local.hidden.includes(key)) hidden.add(key); else hidden.delete(key);
  }
  result.hidden = result.order.filter(key => hidden.has(key));
  const domains = [['overlays',3],['objects',2],['tables',1],['textBoxes',2]] as const;
  for (const [field, depth] of domains)
    result[field] = merge(base[field] || {},local[field] || {},remote[field] || {},depth);
  return result;
}
export function saveRequest(accepted: RevisionedSnapshot, job: Snapshot): SaveRequest {
  return {baseRevision: accepted.revision, baseSourceRevision: accepted.sourceRevision,
    baseSlideRevisions: accepted.slideRevisions, baseSnapshot: snapshot(accepted),
    snapshot: job, compact: true};
}

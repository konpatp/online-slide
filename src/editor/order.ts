/** Move one permanent identity, never reconstruct state from DOM indexes. */
export function moveBefore(order: readonly string[], id: string, before: string | null): string[] {
  return moveManyBefore(order, [id], before);
}

/** Move a selection as one transaction, preserving its original deck order. */
export function moveManyBefore(order: readonly string[], ids: readonly string[], before: string | null): string[] {
  const selected = new Set(ids);
  if (!ids.length || ids.some(id => !order.includes(id)) ||
      (before !== null && (!order.includes(before) || selected.has(before)))) return [...order];
  const moving = order.filter(id => selected.has(id));
  const next = order.filter(id => !selected.has(id));
  next.splice(before === null ? next.length : next.indexOf(before), 0, ...moving);
  return next;
}

/** Move one permanent identity, never reconstruct state from DOM indexes. */
export function moveBefore(order: readonly string[], id: string, before: string | null): string[] {
  if (!order.includes(id) || (before !== null && !order.includes(before))) return [...order];
  if (id === before) return [...order];
  const next = order.filter(key => key !== id);
  next.splice(before === null ? next.length : next.indexOf(before), 0, id);
  return next;
}

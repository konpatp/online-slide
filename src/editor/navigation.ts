/** One sequence owns audience navigation, counts and hidden-route resolution. */
export function navigationOrder(order: readonly string[], hidden: readonly string[], presenting: boolean): string[] {
  const excluded=new Set(hidden);
  return order.filter(id=>!presenting || !excluded.has(id));
}
export function visibleDestination(order: readonly string[], visible: readonly string[], requested: string): string | null {
  if(visible.includes(requested)) return requested;
  const allowed=new Set(visible);
  return order.slice(Math.max(0,order.indexOf(requested))).find(id=>allowed.has(id)) || visible[visible.length-1] || null;
}

// Displayed numeric values own their colors, including live curator edits.
export const HEAT_COLORS = ['#168b80', '#f2cf62', '#c94f35'];
export function numericCell(text: string): number | null {
  const value=String(text).trim();
  return /^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(value) && Number.isFinite(Number(value)) ? Number(value) : null;
}
export function heatDomain(values: Array<number | null>): number[] | null {
  const numbers=values.filter((value): value is number=>value!==null && Number.isFinite(value));
  return numbers.length ? [Math.min(...numbers),Math.max(...numbers)] : null;
}
export function heatColor(value: number | null,domain: number[] | null) {
  if(value===null || !Number.isFinite(value) || !domain) return null;
  const t=domain[1]===domain[0] ? .5 : Math.max(0,Math.min(1,(value-domain[0])/(domain[1]-domain[0])));
  const index=t<=.5?0:1, f=t<=.5?t*2:(t-.5)*2;
  const rgb=HEAT_COLORS.slice(index,index+2).map(hex=>[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)));
  const mixed=rgb[0].map((n,i)=>Math.round(n+(rgb[1][i]-n)*f));
  const linear=mixed.map(n=>{const s=n/255;return s<=.04045?s/12.92:((s+.055)/1.055)**2.4;});
  const luminance=.2126*linear[0]+.7152*linear[1]+.0722*linear[2];
  const white=1.05/(luminance+.05),black=(luminance+.05)/.05;
  return {background:'rgb('+mixed.join(', ')+')',foreground:white>black?'#ffffff':'#000000',
          contrast:Math.max(white,black),value};
}

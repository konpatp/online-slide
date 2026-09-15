// Displayed numeric values own their colors, including live curator edits.
export const HEAT_COLORS = ['#168b80', '#f2cf62', '#c94f35'];
export function numericCell(text: string): number | null {
  const value=String(text).trim();
  return /^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(value) && Number.isFinite(Number(value)) ? Number(value) : null;
}
export type HeatScale = 'log' | 'linear';
export function heatDomain(values: Array<number | null>, scale: HeatScale = 'log'): number[] | null {
  const numbers=values.filter((value): value is number=>value!==null && Number.isFinite(value) && (scale==='linear' || value>0)).sort((a,b)=>a-b);
  if(!numbers.length) return null;
  const transformed=numbers.map(v=>scale==='log'?Math.log(v):v);
  const quantile=(p:number)=>{
    const position=(transformed.length-1)*p, i=Math.floor(position), f=position-i;
    return transformed[i]+(transformed[Math.min(i+1,transformed.length-1)]-transformed[i])*f;
  };
  // Tukey fences in display space: extreme failures do not consume the ramp.
  // Keep all observations in the table; only the color domain excludes them.
  if(numbers.length>=4) {
    const q1=quantile(.25),q3=quantile(.75),iqr=q3-q1;
    const kept=numbers.filter((_,i)=>transformed[i]>=q1-1.5*iqr && transformed[i]<=q3+1.5*iqr);
    if(kept.length) return [kept[0],kept[kept.length-1]];
  }
  return [numbers[0],numbers[numbers.length-1]];
}
export function heatColor(value: number | null,domain: number[] | null,scale: HeatScale = 'log') {
  if(value===null || !Number.isFinite(value) || !domain || (scale==='log' && (value<=0 || domain[0]<=0))) return null;
  const transform=(v:number)=>scale==='log'?Math.log(v):v;
  const t=domain[1]===domain[0] ? (value<domain[0]?0:value>domain[1]?1:.5) : Math.max(0,Math.min(1,(transform(value)-transform(domain[0]))/(transform(domain[1])-transform(domain[0]))));
  const index=t<=.5?0:1, f=t<=.5?t*2:(t-.5)*2;
  const rgb=HEAT_COLORS.slice(index,index+2).map(hex=>[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)));
  const mixed=rgb[0].map((n,i)=>Math.round(n+(rgb[1][i]-n)*f));
  const linear=mixed.map(n=>{const s=n/255;return s<=.04045?s/12.92:((s+.055)/1.055)**2.4;});
  const luminance=.2126*linear[0]+.7152*linear[1]+.0722*linear[2];
  const white=1.05/(luminance+.05),black=(luminance+.05)/.05;
  return {background:'rgb('+mixed.join(', ')+')',foreground:white>black?'#ffffff':'#000000',
          contrast:Math.max(white,black),value};
}

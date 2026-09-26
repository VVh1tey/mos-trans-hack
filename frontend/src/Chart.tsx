import { useEffect, useId, useRef, useState } from 'react';
type Point = { label: string; a: number; b: number };
export function Chart({ points, labels = ['Максимальное', 'Среднее'], unit = 'мин' }: { points: Point[]; labels?: string[]; unit?: string }) {
  const id = useId().replaceAll(':','');
  const container = useRef<HTMLDivElement>(null);
  const [measuredWidth, setMeasuredWidth] = useState(860);
  useEffect(()=>{if(!container.current)return;const observer=new ResizeObserver(entries=>setMeasuredWidth(entries[0].contentRect.width));observer.observe(container.current);return()=>observer.disconnect();},[]);
  const [hover, setHover] = useState<number | null>(null);
  const width = Math.max(300, measuredWidth), height = 195, top = 12, bottom = 163, left = 34, right = width-20;
  const labelStep = width < 500 ? 8 : 4;
  const max = Math.max(5, Math.ceil(Math.max(...points.flatMap(p=>[p.a,p.b]))/5)*5);
  const x = (i: number) => left+i*(right-left)/Math.max(1,points.length-1);
  const y = (v: number) => bottom-v/max*(bottom-top);
  const line = (key: 'a' | 'b') => points.map((p,i)=>`${i?'L':'M'}${x(i)},${y(p[key])}`).join(' ');
  return <div className="chart" ref={container}>
    <div className="chart-legend"><span><i className="chart-dot primary"/>{labels[0]}</span><span><i className="chart-dot secondary"/>{labels[1]}</span><small>{unit}</small></div>
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${labels.join(' и ')}: график в ${unit}`} onMouseLeave={()=>setHover(null)}>
      <defs><linearGradient id={id} x1="0" y1="0" x2="0" y2="1"><stop stopColor="#930c39" stopOpacity=".12"/><stop offset="1" stopColor="#930c39" stopOpacity=".02"/></linearGradient></defs>
      {[0,1,2,3].map(i=><g key={i}><line x1={left} x2={right} y1={y(max*i/3)} y2={y(max*i/3)} stroke="#e9edf0"/><text x={left-10} y={y(max*i/3)+4} textAnchor="end">{Math.round(max*i/3)}</text></g>)}
      {points.filter((_,i)=>i%labelStep===0).map((p,i)=><g key={i}><line x1={x(i*labelStep)} x2={x(i*labelStep)} y1={top} y2={bottom} stroke="#f0f2f5"/><text x={x(i*labelStep)} y={188} textAnchor="middle">{p.label}</text></g>)}
      <path d={`${line('a')} L${right},${bottom} L${left},${bottom}Z`} fill={`url(#${id})`}/>
      <path d={line('b')} fill="none" stroke="#e3a2b6" strokeWidth="2"/>
      <path d={line('a')} fill="none" stroke="#930c39" strokeWidth="2.5" strokeLinejoin="round"/>
      {points.map((p,i)=><rect key={i} x={x(i)-15} y={top} width={30} height={bottom-top} fill="transparent" onMouseEnter={()=>setHover(i)}><title>{p.label}: {labels[0]} {p.a.toFixed(1)}, {labels[1]} {p.b.toFixed(1)} {unit}</title></rect>)}
      {hover!==null && <g><line x1={x(hover)} x2={x(hover)} y1={top} y2={bottom} stroke="#8a7180" strokeDasharray="3 3"/><circle cx={x(hover)} cy={y(points[hover].a)} r="4" fill="#930c39"/></g>}
    </svg>
    {hover!==null && <div className="chart-reading">{points[hover].label} · {labels[0]}: {points[hover].a.toFixed(1)} {unit} · {labels[1]}: {points[hover].b.toFixed(1)} {unit}</div>}
  </div>;
}

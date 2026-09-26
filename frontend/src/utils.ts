import type { Risk } from './types';
export const riskLabels: Record<Risk,string> = { low: 'Низкий', medium: 'Средний', high: 'Высокий' };
export const delay = (seconds: number) => `${seconds > 0 ? '+' : seconds < 0 ? '−' : ''}${Math.floor(Math.abs(seconds)/60)}:${String(Math.abs(seconds)%60).padStart(2,'0')}`;
export const time = (iso: string) => new Date(iso).toLocaleTimeString('ru-RU', { hour:'2-digit',minute:'2-digit',timeZone:'Europe/Moscow' });
export const age = (seconds: number) => seconds < 60 ? `${seconds} сек назад` : `${Math.floor(seconds/60)} мин назад`;
export function routeHref(id: string, tab = 'overview') { const q = new URLSearchParams(window.location.search); q.set('route',id); q.set('view','routes'); q.set('tab',tab); q.delete('vehicle'); return `/?${q}`; }
export function downloadCsv(rows: string[][], name: string) {
  const csv = '\ufeff'+rows.map(row=>row.map(cell=>'"'+cell.replaceAll('"','""')+'"').join(';')).join('\r\n');
  const url = URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
  const a = document.createElement('a'); a.href=url; a.download=name; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
}

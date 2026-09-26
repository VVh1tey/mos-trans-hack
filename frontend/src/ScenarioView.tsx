import { useState, lazy, Suspense } from 'react';
import { BusFront, Info, Minus, Play, Plus, ArrowRight, LoaderCircle } from 'lucide-react';
import { api } from './api';
import { Chart } from './Chart';
import type { Route, Scenario, Settings, Vehicle } from './types';
const TransportMap=lazy(()=>import('./TransportMap'));
export function ScenarioView({route,settings,onSelect,direction,onDirection}: {route:Route;settings:Settings;onSelect:(v:Vehicle)=>void;direction:number;onDirection:(v:number)=>void}) {
  const [count,setCount]=useState(1), [stop,setStop]=useState(route.stops[0]?.id||''), [start,setStart]=useState('01:15'), [horizon,setHorizon]=useState(60);
  const [result,setResult]=useState<Scenario|null>(null), [busy,setBusy]=useState(false), [error,setError]=useState('');
  const parameters={extraVehicles:count,horizonMinutes:horizon,direction,startStopId:stop,startTime:start};
  const outdated=result && JSON.stringify(result.parameters)!==JSON.stringify(parameters);
  async function calculate(event:React.FormEvent) {
    event.preventDefault();setBusy(true);setError('');
    try {setResult(await api.scenario(route.id,parameters));} catch(e){setError((e as Error).message);} finally {setBusy(false);}
  }
  return <div className="scenario-layout">
    <form className="panel scenario-form" onSubmit={calculate}>
      <h2>Параметры сценария</h2>
      <label>Маршрут<div className="readonly-field"><BusFront size={19}/>Маршрут {route.number}</div></label>
      <label>Направление<select value={direction} onChange={e=>onDirection(Number(e.target.value))}><option value={0}>Прямое направление</option>{route.directionCount>1 && <option value={1}>Обратное направление</option>}</select></label>
      <label>Дополнительные ТС<span className="stepper"><button type="button" aria-label="Убрать одно ТС" onClick={()=>setCount(v=>Math.max(1,v-1))} disabled={count===1}><Minus size={17}/></button><output>+{count} ТС</output><button type="button" aria-label="Добавить одно ТС" onClick={()=>setCount(v=>Math.min(5,v+1))} disabled={count===5}><Plus size={17}/></button></span></label>
      <label>Остановка выпуска<select value={stop} onChange={e=>setStop(e.target.value)}>{route.stops.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
      <label>Время выпуска, МСК<input type="time" value={start} required onChange={e=>setStart(e.target.value)}/></label>
      <label>Горизонт моделирования<select value={horizon} onChange={e=>setHorizon(Number(e.target.value))}><option value={30}>30 минут</option><option value={60}>60 минут</option><option value={120}>120 минут</option></select></label>
      {error && <p className="form-error" role="alert">{error}</p>}
      <button className="primary-button calculate" disabled={busy} type="submit">{busy?<LoaderCircle className="spin" size={18}/>:<Play size={18}/>} {busy?'Рассчитываем…':'Рассчитать сценарий'}</button>
      <p className="help-text">Расчёт не выпускает ТС на линию. Параметры используются только для сравнения сценариев.</p>
    </form>
    <div className="scenario-content">
      <Suspense fallback={<div className="map-panel skeleton"/>}><TransportMap routes={[route]} routeMode settings={settings} onSelect={onSelect} extraStop={route.stops.find(s=>s.id===stop)?.coordinates}/></Suspense>
      <section className="panel scenario-results"><div className="section-heading"><h2>Ожидаемые результаты сценария</h2><span className="subtle"><Info size={14}/>Демонстрационная оценка</span></div>
        {result ? <><p className="scenario-disclaimer">{result.notice}</p>{outdated && <p className="inline-warning" role="status">Параметры изменены. Рассчитайте сценарий заново.</p>}<div className={`comparison-grid ${outdated?'outdated':''}`}>{result.metrics.map(m=><div className="comparison" key={m.label}><h3>{m.label}</h3><div className="comparison-labels"><span>Базовый план</span><span>Сценарий</span></div><div className="comparison-values"><strong>{m.baseline.toLocaleString('ru-RU')} <small>{m.unit}</small></strong><ArrowRight size={18}/><strong className="good">{m.scenario.toLocaleString('ru-RU')} <small>{m.unit}</small></strong></div><span className="change-badge">−{(m.baseline-m.scenario).toLocaleString('ru-RU',{maximumFractionDigits:1})} {m.unit} ({Math.round((m.scenario/m.baseline-1)*100)}%)</span></div>)}</div></>:<div className="scenario-empty"><Info size={22}/><div><strong>Проверьте решение до выпуска ТС</strong><p>Выберите остановку и время, затем рассчитайте сценарий. Здесь появится сравнение с базовым планом.</p></div></div>}
      </section>
      <section className="panel chart-panel"><div className="section-heading"><h2>Интервал движения на ближайшие {result?.parameters.horizonMinutes??horizon} минут</h2></div>{result?<Chart points={result.series.map(p=>({label:`+${p.minute} мин`,a:p.scenario,b:p.baseline}))} labels={['Сценарий','Базовый план']}/>:<div className="empty-state compact">График появится после расчёта</div>}</section>
    </div>
  </div>;
}

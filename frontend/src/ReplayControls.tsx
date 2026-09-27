import { useEffect, useRef, useState } from 'react';
import { BusFront, Clock3, Gauge, LoaderCircle, Pause, Play, RotateCcw, Target } from 'lucide-react';
import { api } from './api';
import { delay, delayRisk, riskLabels } from './utils';
import type { Settings, SimulationStatus, TelemetryVehicle } from './types';

export const replayTime = (value: number, date = false) => new Date(value * 1000).toLocaleString('ru-RU', { timeZone:'Europe/Moscow', ...(date ? {day:'2-digit', month:'2-digit'} as const : {}), hour:'2-digit', minute:'2-digit', second:'2-digit' });
export function useSimulation() {
  const [state, setState] = useState<SimulationStatus | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const generation = useRef(0), controlling = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      const version = generation.current;
      try {
        if (!controlling.current) {
          const next = await api.simulation(controller.signal);
          if (!controller.signal.aborted && generation.current === version) { setState(next); setError(''); }
        }
      } catch (e) { if (!controller.signal.aborted && generation.current === version) setError((e as Error).message); }
      finally { if (!controller.signal.aborted) timer = setTimeout(poll, 1000); }
    }
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [refresh]);
  async function control(action: 'start' | 'stop' | 'reset' | 'speed', speed?: number) {
    if (controlling.current) return;
    controlling.current = true; generation.current++; setBusy(true); setError('');
    try { setState(await api.controlSimulation(action, speed)); }
    catch (e) { setError((e as Error).message); }
    finally { controlling.current = false; setBusy(false); }
  }
  return {state, error, busy, control, retry: () => setRefresh(v => v+1)};
}

export function ReplayControls({simulation}: {simulation: ReturnType<typeof useSimulation>}) {
  const {state, error, busy, control, retry} = simulation;
  const label = !state ? 'Загрузка данных…' : !state.available ? 'Данные недоступны' : state.completed ? 'Воспроизведение завершено' : state.running ? 'Воспроизведение идёт' : state.started ? 'Пауза' : 'Готово к запуску';
  return <section className="panel replay-controls" aria-label="Воспроизведение тестовых данных">
    <div className="replay-control-row"><div className="replay-title"><strong>Исторические данные · test</strong><span>{state?.available ? `${state.trafficRows.toLocaleString('ru-RU')} записей · ${state.scheduleRows.toLocaleString('ru-RU')} прибытий в расписании` : 'Полные traffic.csv и schedule.csv'}</span></div>
      <div className="replay-actions"><label>Скорость<select aria-label="Скорость воспроизведения" value={state?.speed || 60} disabled={busy || !state?.available} onChange={e => void control('speed', Number(e.target.value))}>{[1,10,60,300,3600].map(v => <option key={v} value={v}>×{v}</option>)}</select></label>
        <button className="primary-button" disabled={busy || !state?.available || (!state.running && !state.ingestAvailable)} onClick={() => void control(state?.running ? 'stop' : 'start')}>{busy ? <LoaderCircle size={16} className="spin"/> : state?.running ? <Pause size={16}/> : <Play size={16}/>} {state?.running ? 'Пауза' : state?.completed ? 'Запустить заново' : state?.started ? 'Продолжить' : 'Запустить'}</button>
        <button disabled={busy || !state?.available || !state.started} onClick={() => void control('reset')}><RotateCcw size={16}/>С начала</button>
      </div></div>
    <div className="replay-timeline"><span>{error ? 'Нет связи с сервером' : label}</span><strong>{state?.available ? replayTime(state.currentTime, true) : '—'} МСК</strong><progress aria-label="Прогресс воспроизведения" max={1} value={state?.progress || 0}/><span>{Math.round((state?.progress || 0)*100)}%</span></div>
    {state?.available && !state.predictionCount && <p className="replay-note">Прогноз появляется только при поступлении пакета для ТС с остановкой через 10–15 минут.{state.firstEligibleAt && state.currentTime < state.firstEligibleAt ? ` Первое такое окно в test — ${replayTime(state.firstEligibleAt)} МСК.` : ''}</p>}
    {(error || state?.errors.length) ? <div className="replay-error" role="alert"><span>{error || state?.errors.join(' ')}</span><button onClick={retry}>Повторить</button></div> : null}
  </section>;
}

export function ReplayMetrics({state}: {state: SimulationStatus | null}) {
  const count = state?.telemetry?.vehicles.filter(v => v.locationValid && !v.stale).length ?? 0;
  const metrics = [
    {name:'ТС на карте', value:count, Icon:BusFront},
    {name:'Обработано записей', value:(state?.sentRows || 0).toLocaleString('ru-RU'), Icon:Gauge},
    {name:'Прогнозов модели', value:state?.predictionCount || 0, Icon:Target},
    {name:'MAE на размеченных, сек', value:state?.maeSeconds == null ? '—' : state.maeSeconds.toFixed(1), Icon:Gauge},
    {name:'Прибытий по плану', value:(state?.scheduleReached || 0).toLocaleString('ru-RU'), Icon:Clock3},
  ];
  return <div className="metrics replay-metrics">{metrics.map(({name,value,Icon}) => <div className="metric" key={name}><span className="metric-icon"><Icon size={26}/></span><div><span className="metric-label">{name}</span><div className="metric-value">{value}</div></div></div>)}</div>;
}

export function ReplayDetails({state, selected, settings, onClear}: {state: SimulationStatus | null; selected: TelemetryVehicle | null; settings: Settings; onClear: () => void}) {
  if (!selected) return <section className="panel replay-details replay-details-empty" aria-label="Данные транспортного средства"><h2>Карточка ТС</h2><p>Выберите транспортное средство на карте, чтобы увидеть его телеметрию и прогноз.</p></section>;
  const recent=(state?.predictions||[]).filter(p=>p.vehicleId===selected.vehicleId&&p.at<=selected.eventTime);
  const predictions=(recent.length ? recent : selected.prediction ? [selected.prediction] : []).slice(0,5);
  const forecast=selected.prediction;
  const riskValue=forecast?.prediction ?? selected.observedDelaySeconds;
  const risk=riskValue == null ? null : delayRisk(riskValue,settings);
  const freshness=selected.stale || selected.positionExpired ? 'Данные устарели' : selected.gpsStatus==='suspect' ? 'Координата отклонена' : selected.gpsStatus==='lost' ? 'GPS потерян' : selected.gpsStatus==='poor' ? 'Слабый GPS' : 'Данные свежие';
  return <section className="panel replay-details" aria-label={`Карточка ТС №${selected.vehicleId}`}>
    <div className="section-heading"><h2>ТС №{selected.vehicleId}</h2><button type="button" className="text-button" onClick={onClear}>Снять выбор</button></div>
    <div className="replay-summary"><span className={`replay-risk ${risk || 'unknown'}`}><i/>{risk ? `${riskLabels[risk]} риск${forecast?' по прогнозу':' по текущему отклонению'}` : 'Риск пока не определён'}</span><span className={selected.stale?'stale':'muted'}>{freshness}</span></div>
    <div className="replay-forecast"><strong className={risk || ''}>{forecast ? delay(Math.round(forecast.prediction)) : '—'}</strong><span>{forecast ? 'Прогноз задержки на целевой остановке' : 'Прогноз задержки пока не рассчитан'}</span>{forecast && <small>План {replayTime(forecast.targetAt,true)} МСК · модель {forecast.model}</small>}</div>
    <div className="replay-vehicle-details"><dl><div><dt>Следующая остановка</dt><dd>{selected.nextStop?.name || (selected.scheduleCount ? 'Расписание завершено' : 'Нет расписания для этого ТС')}</dd></div>{selected.nextStop && <div><dt>Прибытие по плану</dt><dd>{replayTime(selected.nextStop.plannedAt,true)} МСК</dd></div>}<div><dt>Текущее отклонение</dt><dd>{selected.observedDelaySeconds == null ? 'Нет наблюдения' : delay(Math.round(selected.observedDelaySeconds))}</dd></div><div><dt>Скорость</dt><dd>{selected.speedKmh} км/ч</dd></div><div><dt>Последний пакет</dt><dd>{replayTime(selected.eventTime)} МСК · {Math.round(selected.ageSeconds)} сек назад</dd></div><div><dt>GPS</dt><dd>{selected.gpsStatus || 'Статус неизвестен'} · {selected.satellites} спутников</dd></div></dl></div>
    <div className="replay-evaluation"><h3>Последние прогнозы</h3>{predictions.length ? predictions.map(p => <div className="replay-prediction" key={p.sampleId}><strong>{p.source==='stream'?'По потоку':'Контрольная точка'}<span>{replayTime(p.at)}</span></strong><div>Остановка по плану {replayTime(p.targetAt)} · прогноз {delay(Math.round(p.prediction))}</div><div>{p.actual == null ? 'Фактическое прибытие ожидается' : `Факт ${delay(Math.round(p.actual))} · ошибка ${Math.round(p.absoluteError!)} сек`}</div></div>) : <p>Для этого ТС пока нет остановки в окне 10–15 минут или не поступил подходящий пакет.</p>}<p className="replay-note">Вероятность задержки модель не рассчитывает. MAE считается только по размеченным контрольным точкам.</p></div>
  </section>;
}

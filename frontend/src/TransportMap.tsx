import { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import { Crosshair, Layers, MapPin, Minus, Plus, RotateCcw } from 'lucide-react';
import type { Route, Settings, Vehicle } from './types';
import { riskLabels } from './utils';
maplibregl.setWorkerUrl(workerUrl);

type Props = { routes: Route[]; settings: Settings; routeMode?: boolean; selected?: Vehicle | null; onSelect: (vehicle: Vehicle) => void; onRouteSelect?: (id: string) => void; extraStop?: [number,number] | null };
export default function TransportMap({ routes, settings, routeMode = false, selected, onSelect, onRouteSelect, extraStop }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const current = useRef({ onSelect, routeMode, onRouteSelect }); current.current = { onSelect, routeMode, onRouteSelect };
  const fitRef = useRef<()=>void>(()=>{});
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [tilesFailed, setTilesFailed] = useState(false);
  const [showStops, setShowStops] = useState(true);
  const [retry, setRetry] = useState(0);
  const lastFrame = useRef('');
  useEffect(()=>{
    if (!container.current) return;
    let map: maplibregl.Map;
    try {
      map = new maplibregl.Map({ container: container.current, center:[37.62,55.75], zoom:10.3, attributionControl:false,
        style:{version:8,sources:{basemap:{type:'raster',tiles:[import.meta.env.VITE_MAP_TILE_URL || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'],tileSize:256,attribution:'© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors',maxzoom:19}},layers:[{id:'background',type:'background',paint:{'background-color':'#e8ece7'}},{id:'basemap',type:'raster',source:'basemap',paint:{'raster-saturation':-.6,'raster-opacity':.78}}]}});
      mapRef.current = map;
      map.addControl(new maplibregl.AttributionControl({compact:true}), 'bottom-right');
      map.addControl(new maplibregl.ScaleControl({maxWidth:90,unit:'metric'}), 'bottom-right');
      map.on('load',()=>{ setReady(true); });
      map.on('error', (event)=>{ if (/worker/i.test(event.error?.message || '')) setFailed(true); else setTilesFailed(true); });
      map.on('click','route-hit', e=>{const id=e.features?.[0]?.properties?.routeId; if(id && !current.current.routeMode) current.current.onRouteSelect?.(String(id));});
      map.on('mouseenter','route-hit',()=>{map.getCanvas().style.cursor='pointer';});
      map.on('mouseleave','route-hit',()=>{map.getCanvas().style.cursor='';});
    } catch { setFailed(true); return; }
    const observer = new ResizeObserver(()=>map.resize()); observer.observe(container.current);
    return ()=>{observer.disconnect(); map.remove(); mapRef.current=null; setReady(false); lastFrame.current='';};
  },[retry]);
  useEffect(()=>{
    const map = mapRef.current;
    if (!ready || !map) return;
    const lines: GeoJSON.Feature<GeoJSON.LineString>[] = [];
    for (const r of routes) {
      const chunks=routeMode ? r.vehicles.length : 1;
      for(let i=0;i<chunks;i++) {
        const start=Math.floor(i*(r.coordinates.length-1)/chunks), end=Math.floor((i+1)*(r.coordinates.length-1)/chunks)+1;
        lines.push({type:'Feature',properties:{routeId:r.id,color:settings.colors[routeMode?r.vehicles[i].risk:r.risk]},geometry:{type:'LineString',coordinates:r.coordinates.slice(start,end)}});
      }
    }
    const collection: GeoJSON.FeatureCollection = {type:'FeatureCollection',features:lines};
    const source=map.getSource('routes') as maplibregl.GeoJSONSource | undefined;
    if(source) source.setData(collection);
    else {
      map.addSource('routes',{type:'geojson',data:collection});
      map.addLayer({id:'route-casing',type:'line',source:'routes',layout:{'line-join':'round','line-cap':'round'},paint:{'line-color':'#fff','line-width':routeMode?7:5,'line-opacity':.9}});
      map.addLayer({id:'route-lines',type:'line',source:'routes',layout:{'line-join':'round','line-cap':'round'},paint:{'line-color':['get','color'],'line-width':routeMode?4:2.5,'line-opacity':routeMode?1:.8}});
      map.addLayer({id:'route-hit',type:'line',source:'routes',paint:{'line-width':18,'line-opacity':0}});
    }
    const markers: maplibregl.Marker[]=[];
    routes.forEach(r=>{
      r.vehicles.forEach(v=>{
        const el=document.createElement('button'); el.type='button'; el.className='vehicle-marker';
        el.style.background=settings.colors[v.risk]; el.title=`Маршрут ${v.routeNumber} · ТС ${v.id}`; el.setAttribute('aria-label',el.title);
        el.innerHTML='<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="5" y="3" width="14" height="17" rx="3"/><path d="M5 11h14M8 20v2m8-2v2M8 6h8"/><circle cx="8.5" cy="16" r=".8"/><circle cx="15.5" cy="16" r=".8"/></svg>';
        el.addEventListener('click',()=>current.current.onSelect(v));
        markers.push(new maplibregl.Marker({element:el}).setLngLat(v.coordinates).addTo(map));
      });
      if (routeMode && showStops) r.stops.forEach(s=>{
        const el=document.createElement('button'); el.type='button'; el.className='stop-marker'; el.title=s.name; el.setAttribute('aria-label',`Остановка ${s.name}`);
        const popupContent=document.createElement('div'); popupContent.textContent=`${s.name} · приближённая привязка`;
        markers.push(new maplibregl.Marker({element:el}).setLngLat(s.coordinates).setPopup(new maplibregl.Popup({offset:12}).setDOMContent(popupContent)).addTo(map));
      });
    });
    fitRef.current=()=>{
      if(!routes.length) return;
      const bounds=new maplibregl.LngLatBounds(); routes.forEach(r=>r.coordinates.forEach(p=>bounds.extend(p)));
      map.fitBounds(bounds,{padding:routeMode?65:35,maxZoom:13,duration:0});
    };
    const frame=routes.map(r=>r.id+':'+r.direction).join('|');
    if(frame!==lastFrame.current){ fitRef.current(); lastFrame.current=frame; }
    return ()=>markers.forEach(m=>m.remove());
  },[ready,routes,settings,showStops,routeMode]);
  useEffect(()=>{
    const map=mapRef.current; if(!map || !ready || !selected) return;
    map.easeTo({center:selected.coordinates,zoom:Math.max(12,map.getZoom()),duration:window.matchMedia('(prefers-reduced-motion: reduce)').matches?0:450});
    const el=document.createElement('div'); el.className='selected-marker';
    const marker=new maplibregl.Marker({element:el}).setLngLat(selected.coordinates).addTo(map);
    return ()=>{marker.remove();};
  },[selected,ready]);
  useEffect(()=>{
    if(!extraStop || !ready || !mapRef.current) return;
    const el=document.createElement('div'); el.className='extra-marker'; el.textContent='+'; el.title='Место выпуска дополнительного ТС';
    const marker=new maplibregl.Marker({element:el}).setLngLat(extraStop).addTo(mapRef.current);
    return ()=>{marker.remove();};
  },[extraStop,ready]);
  return <div className="map-panel" aria-label="Карта маршрутов Москвы">
    <div ref={container} className="map-canvas"/>
    {failed ? <div className="map-fallback"><MapPin size={30}/><strong>Карта недоступна</strong><span>Для карты нужен WebGL. Данные маршрутов доступны в таблице.</span><button onClick={()=>{setFailed(false);setRetry(v=>v+1);}}><RotateCcw size={16}/>Повторить</button></div> : <>
      {!ready && <div className="map-loading">Загрузка карты Москвы…</div>}
      <div className="map-tools"><button aria-label="Приблизить карту" onClick={()=>mapRef.current?.zoomIn()}><Plus size={19}/></button><button aria-label="Отдалить карту" onClick={()=>mapRef.current?.zoomOut()}><Minus size={19}/></button><button aria-label="Показать весь маршрут" onClick={()=>fitRef.current()}><Crosshair size={19}/></button>{routeMode && <button aria-label="Показать остановки" aria-pressed={showStops} onClick={()=>setShowStops(!showStops)}><Layers size={19}/></button>}</div>
      <div className="map-caption"><MapPin size={14}/>{routeMode?'Геометрия маршрута':'Москва · ночная сеть'}<span>{routes.length} {routeMode?'маршрут':'маршрутов'}</span></div>
      <div className="map-legend"><strong>Риск задержки</strong>{(['low','medium','high'] as const).map(r=><span key={r}><i style={{background:settings.colors[r]}}/>{riskLabels[r]}</span>)}</div>
      {tilesFailed && <div className="map-warning">Подложка недоступна. Геометрия маршрутов сохранена.</div>}
      {!routes.length && ready && <div className="map-empty">Нет маршрутов по выбранным фильтрам</div>}
    </>}
  </div>;
}

"""Deterministic demo provider. Replace this module with online repositories later."""
import copy
import json
import math
import csv
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

CATALOG = json.loads((Path(__file__).parent / 'demo/routes.json').read_text(encoding='utf-8'))
for _route in CATALOG['routes']:
    _route.setdefault('serviceType', 'night')
IMPORT_DIR = Path(os.environ.get('ROUTES_IMPORT_DIR', Path(__file__).resolve().parents[1] / 'data' / 'moscowmap'))
SETTINGS = {'mediumDelaySeconds': 120, 'highDelaySeconds': 420, 'staleAfterSeconds': 90,
            'colors': {'low': '#24855b', 'medium': '#bd7608', 'high': '#b52238'}}


def stamp(dt):
    return dt.isoformat().replace('+00:00', 'Z')


def risk(delay, settings):
    return 'high' if delay >= settings['highDelaySeconds'] else 'medium' if delay >= settings['mediumDelaySeconds'] else 'low'


def settings_from(body):
    if not isinstance(body, dict):
        raise ValueError('Ожидается объект настроек')
    values = {key: body.get(key, SETTINGS[key]) for key in ('mediumDelaySeconds', 'highDelaySeconds', 'staleAfterSeconds')}
    if any(type(v) is not int for v in values.values()):
        raise ValueError('Пороги должны быть целыми числами секунд')
    if not 0 < values['mediumDelaySeconds'] < values['highDelaySeconds'] <= 3600:
        raise ValueError('Средний порог должен быть меньше высокого; максимум 3600 секунд')
    if not 15 <= values['staleAfterSeconds'] <= 3600:
        raise ValueError('Порог свежести: от 15 до 3600 секунд')
    colors = body.get('colors', SETTINGS['colors'])
    import re
    if not isinstance(colors, dict) or set(colors) != {'low', 'medium', 'high'} or any(not isinstance(c, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', c) for c in colors.values()):
        raise ValueError('Укажите три цвета в формате #RRGGBB')
    return {**values, 'colors': colors.copy()}


def summary(vehicles, route_count, settings):
    return {'activeVehicles': len(vehicles),
            'routeCount': route_count, 'highRiskCount': sum(v['risk'] == 'high' for v in vehicles),
            'incidentCount': sum(v['risk'] != 'low' for v in vehicles),
            'averageDelaySeconds': round(sum(v['delaySeconds'] for v in vehicles) / max(1, len(vehicles))),
            'worstDelaySeconds': max((v['delaySeconds'] for v in vehicles), default=0),
            'freshPercent': round(100 * sum(v['ageSeconds'] <= settings['staleAfterSeconds'] for v in vehicles) / max(1, len(vehicles)))}


def imported_routes():
    """Load explicitly supplied route definitions from the shared import folder."""
    routes = []
    if not IMPORT_DIR.is_dir():
        return routes
    for path in sorted(IMPORT_DIR.iterdir()):
        if path.name.startswith('_') or path.stem == 'example' or path.suffix.lower() not in {'.json', '.csv'}:
            continue
        if path.stem in {'routes', 'stops'} and path.suffix.lower() == '.csv':
            continue
        if path.suffix.lower() == '.json':
            value = json.loads(path.read_text(encoding='utf-8-sig'))
            items = value if isinstance(value, list) else value.get('routes', [])
            for item in items:
                if item.get('directions'):
                    routes.append(item)
                    continue
                # MoscowMap provides ordered stop names and route geometry. Its
                # stop coordinates are not exposed consistently, so distribute
                # stops along the published shape and mark that approximation.
                shape = item.get('coordinates') or []
                source_stops = item.get('stops') or []
                if len(shape) < 2 or not source_stops:
                    continue
                has_stop_coordinates = all(stop.get('coordinates') for stop in source_stops)
                stops = []
                for index, stop in enumerate(source_stops):
                    point_index = round(index * max(0, len(shape)-1) / max(1, len(source_stops)-1))
                    if not shape:
                        break
                    coordinate = stop.get('coordinates') or shape[point_index]
                    stops.append({'id': stop.get('id', f"{item['id']}-{stop.get('sequence', index+1)}"),
                                  'name': stop['name'], 'coordinates': coordinate})
                route_id = str(item.get('id') or item.get('number'))
                number = str(item.get('number') or route_id)
                route_type = item.get('transport', 'avtobusy')
                routes.append({'id': route_id, 'number': number, 'name': item.get('title', number),
                               'transport': {'avtobusy': 'bus', 'trolleibusy': 'trolleybus',
                                             'tramvai': 'tram', 'marshrutki': 'minibus',
                                             'rechnoy-transport': 'river'}.get(route_type, route_type),
                               'serviceType': 'day', 'intervalMinutes': 10,
                               'coordinateQuality': 'published shape; stop coordinates parsed from page' if has_stop_coordinates else 'published shape; stops without coordinates interpolated by sequence',
                               'directions': [{'coordinates': shape, 'stops': stops}]})
            continue
        with path.open(encoding='utf-8-sig', newline='') as file:
            for row in csv.DictReader(file):
                row['directions'] = json.loads(row.pop('directions_json'))
                routes.append(row)
    return routes


def history(seed, period, snapshot_at):
    return [{'time': stamp(snapshot_at - timedelta(minutes=period * (24-i)/24)),
             'average': round(85 + i*3 + 35*math.sin(i*.7 + seed)),
             'maximum': round(190 + i*12 + 50*math.sin(i*.8 + seed))} for i in range(25)]


def snapshot(settings=None, route_id=None, direction=0, period=60):
    settings = settings or SETTINGS
    snapshot_at = datetime.now(timezone.utc)
    catalog_routes = copy.deepcopy(CATALOG['routes'])
    by_id = {r['id']: r for r in catalog_routes}
    by_id.update({str(r['id']): r for r in imported_routes()})
    catalog_routes = list(by_id.values())
    routes, all_vehicles, all_incidents = [], [], []
    elapsed = 0
    for index, original in enumerate(catalog_routes):
        if route_id and original['id'] != route_id:
            continue
        if original.get('serviceType') not in ('night', 'day'):
            raise ValueError(f"route {original.get('id')}: serviceType must be 'night' or 'day'")
        if not original.get('directions'):
            raise ValueError(f"route {original.get('id')}: at least one direction is required")
        route = {k: v for k, v in original.items() if k != 'directions'}
        d = min(direction, len(original['directions'])-1)
        shape = original['directions'][d]
        stops = copy.deepcopy(shape['stops'])
        for j, stop in enumerate(stops):
            stop['delaySeconds'] = max(0, round(65*j + 42*math.sin(index+j)))
            stop['scheduledAt'] = stamp(snapshot_at + timedelta(minutes=3*j))
            stop['predictedAt'] = stamp(snapshot_at + timedelta(minutes=3*j, seconds=stop['delaySeconds']))
            stop['risk'] = risk(stop['delaySeconds'], settings)
        vehicles = []
        vehicle_count = max(1, min(9, round(120 / max(1, route.get('intervalMinutes', 10)))))
        for j in range(vehicle_count):
            p = (j+.35)/vehicle_count
            point = shape['coordinates'][int(p*(len(shape['coordinates'])-1))]
            delay = [522, 310, 75, 35, 160, 48, 95, 210, 65][j] + (index % 4)*17
            if index % 5 == 3:
                delay = delay // 6
            level = risk(delay, settings)
            target = stops[min(len(stops)-1, max(1, int(p*len(stops))+1))]
            age = [18, 35, 12, 25, 65, 110, 45, 14, 30][j] + elapsed
            vehicle = {'id': f'{1700+index*20+j}', 'routeId': route['id'], 'routeNumber': route['number'],
                       'coordinates': point, 'delaySeconds': delay, 'risk': level,
                       'probability': min(.97, round(.28+delay/1000, 2)), 'speedKmh': 9+j*4,
                       'targetStop': target['name'], 'targetStopId': target['id'],
                       'observedAt': stamp(snapshot_at-timedelta(seconds=age)), 'ageSeconds': age,
                       'signal': 'Скорость ниже обычной' if j % 2 == 0 else 'Растёт время в пути',
                       'segment': f"{stops[max(0,min(len(stops)-2,int(p*len(stops))))]['name']} → {target['name']}"}
            vehicles.append(vehicle)
            if level != 'low':
                all_incidents.append({**vehicle, 'alertId': f"alert-{vehicle['id']}-{target['id']}", 'status': 'new'})
        route.update({'coordinates': shape['coordinates'], 'stops': stops, 'directionCount': len(original['directions']),
                      'direction': d, 'summary': summary(vehicles, 1, settings),
                      'risk': max((v['risk'] for v in vehicles), key=lambda r: ['low','medium','high'].index(r)),
                      'intervalMinutes': 8+index%5, 'vehicles': vehicles})
        routes.append(route)
        all_vehicles.extend(vehicles)
    if route_id and not routes:
        raise KeyError('Маршрут не найден')
    all_incidents.sort(key=lambda a: -a['delaySeconds'])
    return {'mode': 'demo', 'generatedAt': stamp(snapshot_at), 'servedAt': stamp(datetime.now(timezone.utc)),
            'notice': 'Геометрия реальная. ТС, расписание, прогнозы и вероятности — демонстрационные. Остановки подобраны по близости к линии.',
            'settings': settings, 'summary': summary(all_vehicles, len(routes), settings),
            'routes': routes, 'incidents': all_incidents, 'history': history(0, period, snapshot_at),
            'historyEvents': [{'id': f"event-{a['id']}", 'time': stamp(snapshot_at-timedelta(minutes=i*3)),
                               'routeId': a['routeId'], 'routeNumber': a['routeNumber'], 'vehicleId': a['id'],
                               'message': 'Обновлён прогноз задержки', 'delaySeconds': a['delaySeconds'], 'risk': a['risk']} for i,a in enumerate(all_incidents[:20])]}


def scenario(route_id, body):
    if not isinstance(body, dict):
        raise ValueError('Ожидается объект сценария')
    count, horizon, direction = body.get('extraVehicles'), body.get('horizonMinutes'), body.get('direction', 0)
    if type(count) is not int or not 1 <= count <= 5 or horizon not in (30,60,120) or type(horizon) is not int:
        raise ValueError('Дополнительные ТС: 1–5; горизонт: 30, 60 или 120 минут')
    if type(direction) is not int or direction not in (0, 1):
        raise ValueError('Неверное направление')
    route = snapshot(route_id=route_id, direction=direction)['routes'][0]
    stop_index = next((i for i,s in enumerate(route['stops']) if s['id'] == body.get('startStopId')), None)
    if stop_index is None:
        raise ValueError('Выберите остановку этого маршрута')
    import re
    start = body.get('startTime', '')
    if not isinstance(start, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', start):
        raise ValueError('Время выпуска должно иметь формат ЧЧ:ММ')
    # Transparent illustrative sensitivity, not an ML forecast or an operational recommendation.
    location_factor = 1 - .45*stop_index/max(1,len(route['stops'])-1)
    hour = int(start[:2])
    time_factor = .8 if 7 <= hour <= 10 or 17 <= hour <= 20 else 1
    effect = min(.55, count/(len(route['vehicles'])+count) * location_factor * time_factor * min(1,horizon/60))
    baseline = route['intervalMinutes']
    gaps = 5 + len(route['vehicles'])//2
    high = max(1,route['summary']['highRiskCount'])
    return {'mode': 'demo', 'model': 'illustrative-headway-v1', 'routeId': route_id, 'parameters': body,
            'notice': 'Демонстрационная формула. Пассажиропоток, пробки и реальные ограничения выпуска не учитываются. Не является прогнозом обученной модели.',
            'metrics': [{'label':'Средний интервал','unit':'мин','baseline':baseline,'scenario':round(baseline*(1-effect),1)},
                        {'label':'Разрывы >12 мин','unit':'','baseline':gaps,'scenario':max(0,round(gaps*(1-effect*1.8)))},
                        {'label':'ТС высокого риска','unit':'','baseline':high,'scenario':max(0,round(high*(1-effect*1.6)))}],
            'series': [{'minute':round(i*horizon/24), 'baseline':round(baseline+2*math.sin(i*.8)+i%4*.5,1),
                        'scenario':round((baseline+2*math.sin(i*.8)+i%4*.5)*(1-effect),1)} for i in range(25)]}

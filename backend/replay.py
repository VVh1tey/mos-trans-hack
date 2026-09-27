"""Chronological playback of complete test CSVs through the real NDTP receiver.

Naive dataset timestamps are interpreted as Moscow time. Future actual arrivals
are used only by the evaluator after their historical occurrence, never by ML.
"""
import bisect
import csv
from datetime import datetime, timedelta, timezone
import math
import os
from pathlib import Path
import re
import socket
import threading
import time
from ndtp import encode_handshake, encode_navigation

MOSCOW = timezone(timedelta(hours=3))
SPEEDS = (1, 10, 60, 300, 3600)


def timestamp(value):
    value = datetime.fromisoformat(value)
    return (value if value.tzinfo else value.replace(tzinfo=MOSCOW)).timestamp()


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as source:
        return list(csv.DictReader(source))


def number(value):
    result = float(value) if value else 0.0
    return result if math.isfinite(result) else 0.0


class Dataset:
    def __init__(self, root):
        root = Path(root)
        traffic = read_csv(root / 'test/traffic.csv')
        schedule = read_csv(root / 'test/schedule.csv')
        self.events, self.units, self.schedules, self.facts, self.points = [], {}, {}, {}, {}
        self.traffic_count, self.schedule_count = len(traffic), len(schedule)
        if not traffic or not schedule:
            raise ValueError('Файлы test/traffic.csv и test/schedule.csv не должны быть пустыми')
        for row in traffic:
            unit, vehicle = int(row['unit_id']), str(row['tr_id'])
            if unit in self.units and self.units[unit] != vehicle:
                raise ValueError('Один unit_id соответствует нескольким ТС')
            self.units[unit] = vehicle
            event_time = timestamp(row['event_time'])
            lon, lat = number(row['lon']), number(row['lat'])
            event = {'unitId': unit, 'vehicleId': vehicle, 'eventTime': event_time,
                     'coordinates': [lon, lat], 'locationValid': row['location_valid'].lower() == 'true' and bool(row['lon'] and row['lat']) and abs(lon) <= 180 and abs(lat) <= 90,
                     'speedKmh': number(row['speed']), 'heading': number(row['heading']), 'altitude': number(row['alt'])}
            if abs(lon) > 180 or abs(lat) > 90:
                event['coordinates'] = [0, 0]
            self.events.append((event_time, 0, event))
        self.schedule_times = []
        by_stop = {}
        for row in schedule:
            planned, actual = timestamp(row['time_begin']), timestamp(row['time_fact_begin'])
            geometry = re.fullmatch(r'POINT\s*\(([-\d.]+)\s+([-\d.]+)\)', row['geom'])
            stop = {'id': row['tt_action_item_id'], 'vehicleId': str(row['tr_id']), 'name': row['building_address'],
                    'plannedAt': planned, 'actualAt': actual,
                    'coordinates': [float(geometry[1]), float(geometry[2])] if geometry else None}
            self.schedules.setdefault(stop['vehicleId'], []).append(stop)
            self.facts.setdefault(stop['vehicleId'], []).append(stop)
            self.schedule_times.append(planned)
            by_stop[stop['id']] = stop
        self.schedule_times.sort()
        for vehicle in self.schedules:
            self.schedules[vehicle].sort(key=lambda s: s['plannedAt'])
            self.facts[vehicle].sort(key=lambda s: s['actualAt'])
        self.planned_times = {v: [s['plannedAt'] for s in stops] for v, stops in self.schedules.items()}
        self.fact_times = {v: [s['actualAt'] for s in stops] for v, stops in self.facts.items()}
        # Optional labeled prediction points support honest evaluation of the selected model.
        labels = root / 'labels/labels_test.csv'
        for row in read_csv(labels) if labels.exists() else []:
            point = {key: row[key] for key in ('sample_id', 'tr_id', 'T', 'target_stop_id', 'target_time_begin', 'cur_dev_s')}
            point['cur_dev_s'] = float(point['cur_dev_s'])
            stop = by_stop.get(row['target_stop_id'])
            point['_actual'] = float(row['target_delay_s'])
            point['_revealAt'] = max(timestamp(row['T']), timestamp(row['target_time_begin']), stop['actualAt'] if stop else timestamp(row['target_time_begin']) + float(row['target_delay_s']))
            self.points[row['sample_id']] = point
            self.events.append((timestamp(row['T']), 1, point))
        self.events.sort(key=lambda event: (event[0], event[1]))
        self.start = self.events[0][0]
        self.end = max(self.events[-1][0], max(self.schedule_times), max(s['actualAt'] for stops in self.facts.values() for s in stops), max((p['_revealAt'] for p in self.points.values()), default=self.start))

    def context(self, vehicle, now):
        stops = self.schedules.get(vehicle, [])
        index = bisect.bisect_right(self.planned_times.get(vehicle, []), now)
        next_stop = stops[index] if index < len(stops) else None
        previous = bisect.bisect_right(self.fact_times.get(vehicle, []), now) - 1
        last = self.facts[vehicle][previous] if previous >= 0 else None
        return {'scheduleCount': len(stops),
                'nextStop': {k: next_stop[k] for k in ('id', 'name', 'plannedAt', 'coordinates')} if next_stop else None,
                'observedDelaySeconds': round(last['actualAt']-last['plannedAt']) if last else None}


class Replay:
    def __init__(self, root, host, port, http, ingest_url, ml_url):
        self.root, self.host, self.port = root, host, port
        self.http, self.ingest_url, self.ml_url = http, ingest_url, ml_url
        self.lock = threading.RLock()
        self.dataset = None
        self.running = False
        self.started = False
        self.speed = 60
        self.current = 0
        self.cursor = 0
        self.sent = 0
        self.sockets = {}
        self.predictions = {}
        self.error = None
        self.session = 0
        self.thread = None
        self.wall = time.monotonic()

    def load(self):
        if self.dataset is None:
            self.dataset = Dataset(self.root)
            self.current = self.dataset.start

    def close_sockets(self):
        for connection in self.sockets.values():
            connection.close()
        self.sockets.clear()

    def reset(self):
        self.running = False
        self.close_sockets()
        self.http(self.ingest_url + '/replay/reset', {})
        self.cursor, self.sent, self.current = 0, 0, self.dataset.start
        self.predictions.clear()
        self.session += 1
        self.error = None
        self.started = True

    def control(self, action, speed=None):
        with self.lock:
            self.load()
            if speed is not None:
                if type(speed) not in (int, float) or speed not in SPEEDS:
                    raise ValueError('Скорость должна быть 1, 10, 60, 300 или 3600')
                self.speed = speed
            if action == 'stop':
                self.running = False
                self.close_sockets()
            elif action in ('start', 'reset'):
                self.http(self.ingest_url + '/health')
                if action == 'reset' or not self.started or self.current >= self.dataset.end:
                    self.reset()
                self.error = None
                self.running = action == 'start'
            elif action != 'speed':
                raise ValueError('action must be start, stop, reset or speed')
            self.wall = time.monotonic()
            if self.thread is None:
                self.thread = threading.Thread(target=self.run, daemon=True)
                self.thread.start()

    def send(self, event):
        unit = event['unitId']
        if unit not in self.sockets:
            connection = socket.create_connection((self.host, self.port), timeout=3)
            connection.sendall(encode_handshake(unit))
            self.sockets[unit] = connection
        self.sockets[unit].sendall(encode_navigation(event, self.sent+2))
        self.sent += 1

    def predict(self, point):
        # Explicit allowlist: target_delay_s and future schedule facts never enter inference.
        body = {key: point[key] for key in ('sample_id', 'tr_id', 'T', 'target_stop_id', 'target_time_begin', 'cur_dev_s')}
        result = self.http(self.ml_url + '/predict', body)
        value = float(result['prediction'])
        if not math.isfinite(value):
            raise ValueError('Модель вернула некорректный прогноз')
        self.predictions[point['sample_id']] = {'sampleId': point['sample_id'], 'vehicleId': point['tr_id'],
                                               'at': timestamp(point['T']), 'targetAt': timestamp(point['target_time_begin']),
                                               'prediction': value, 'model': result['model']}

    def advance(self, target, limit=2000):
        processed = 0
        while self.cursor < len(self.dataset.events) and self.dataset.events[self.cursor][0] <= target and processed < limit:
            when, kind, event = self.dataset.events[self.cursor]
            if kind == 0:
                self.send(event)
            else:
                self.predict(event)
            self.cursor += 1
            processed += 1
            self.current = when
        pending = self.cursor < len(self.dataset.events) and self.dataset.events[self.cursor][0] <= target
        if not pending:
            self.current = min(target, self.dataset.end)
        if self.current >= self.dataset.end:
            self.running = False
            self.close_sockets()
        return pending

    def run(self):
        target = None
        while True:
            time.sleep(.1)
            with self.lock:
                if not self.running:
                    target = None
                    self.wall = time.monotonic()
                    continue
                now = time.monotonic()
                target = max(target or self.current, self.current) + (now-self.wall)*self.speed
                self.wall = now
                try:
                    if not self.advance(target):
                        target = None
                except (OSError, ValueError, KeyError) as exc:
                    self.error = f'Воспроизведение приостановлено: {exc}. Проверьте ingest и ML и нажмите «Продолжить».'
                    self.running = False
                    self.close_sockets()

    def snapshot(self, telemetry):
        with self.lock:
            self.load()
            data = self.dataset
            evaluated, predictions = [], []
            for key, prediction in self.predictions.items():
                point = data.points[key]
                actual = point['_actual'] if point['_revealAt'] <= self.current else None
                error = abs(prediction['prediction']-actual) if actual is not None else None
                if error is not None:
                    evaluated.append(error)
                predictions.append({**prediction, 'actual': actual, 'absoluteError': error})
            latest_prediction = {p['vehicleId']: p for p in predictions}
            if telemetry is not None:
                telemetry = {**telemetry, 'vehicles': [
                    {**v, 'vehicleId': data.units[v['unitId']], **data.context(data.units[v['unitId']], self.current),
                     'ageSeconds': max(0, round(self.current-v['eventTime'], 1)), 'stale': self.current-v['eventTime'] > 90,
                     'positionAgeSeconds': max(0, round(self.current-v.get('positionEventTime', v['eventTime']), 1)),
                     'positionExpired': not v.get('hasPosition') or self.current-v.get('positionEventTime', v['eventTime']) > 120,
                     'prediction': latest_prediction.get(data.units[v['unitId']])}
                    for v in telemetry['vehicles'] if self.started and v['unitId'] in data.units and data.start-1 <= v['eventTime'] <= self.current+1]}
            return {'source': 'test', 'available': True, 'running': self.running, 'started': self.started,
                    'completed': self.current >= data.end, 'speed': self.speed, 'currentTime': self.current,
                    'startTime': data.start, 'endTime': data.end, 'session': self.session,
                    'trafficRows': data.traffic_count, 'scheduleRows': data.schedule_count,
                    'vehicleCount': len(data.units), 'scheduledVehicleCount': len(data.schedules),
                    'sentRows': self.sent, 'scheduleReached': bisect.bisect_right(data.schedule_times, self.current),
                    'progress': (self.current-data.start)/max(1, data.end-data.start),
                    'predictionCount': len(predictions), 'predictionTotal': len(data.points), 'evaluatedCount': len(evaluated),
                    'maeSeconds': sum(evaluated)/len(evaluated) if evaluated else None,
                    'predictions': predictions[-20:][::-1], 'telemetry': telemetry,
                    'ingestAvailable': telemetry is not None, 'errors': [self.error] if self.error else []}

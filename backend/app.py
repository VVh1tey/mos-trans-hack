"""HTTP API for dashboard, historical NDTP replay, ML proxy and metrics."""

import json
import os
from pathlib import Path
import resource
import threading
import time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener
from urllib.parse import urlparse, parse_qs
import dashboard
import simulation


ML_URL = os.environ.get("ML_URL", "http://ml:8001")
DIRECT_HTTP = build_opener(ProxyHandler({}))
METRICS_LOCK = threading.Lock()
HTTP_REQUESTS = defaultdict(int)
HTTP_LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
HTTP_LATENCY_COUNTS = defaultdict(lambda: {'buckets': [0] * len(HTTP_LATENCY_BUCKETS), 'count': 0, 'sum': 0.0})
MODEL_REQUESTS = defaultdict(int)
MODEL_LATENCY_COUNTS = defaultdict(lambda: {'buckets': [0] * len(HTTP_LATENCY_BUCKETS), 'count': 0, 'sum': 0.0})


def record_request(handler, started):
    route = urlparse(handler.path).path
    if route.startswith('/api/dashboard/routes/'):
        route = '/api/dashboard/routes/:route'
    status = str(getattr(handler, '_status_code', 500))
    elapsed = time.perf_counter() - started
    key = (handler.command, route, status)
    with METRICS_LOCK:
        HTTP_REQUESTS[key] += 1
        counts = HTTP_LATENCY_COUNTS[key]
        for index, bound in enumerate(HTTP_LATENCY_BUCKETS):
            if elapsed <= bound:
                counts['buckets'][index] += 1
        counts['count'] += 1
        counts['sum'] += elapsed


def record_model_request(model, status, elapsed):
    key = (model, str(status))
    with METRICS_LOCK:
        MODEL_REQUESTS[key] += 1
        data = MODEL_LATENCY_COUNTS[key]
        for index, bound in enumerate(HTTP_LATENCY_BUCKETS):
            if elapsed <= bound:
                data['buckets'][index] += 1
        data['count'] += 1
        data['sum'] += elapsed


def resident_memory_bytes():
    try:
        with open('/proc/self/statm', encoding='ascii') as statm:
            resident_pages = int(statm.read().split()[1])
        return resident_pages * os.sysconf('SC_PAGE_SIZE')
    except (OSError, ValueError, IndexError):
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024


class Handler(BaseHTTPRequestHandler):
    def send_response(self, code, message=None):
        self._status_code = code
        super().send_response(code, message)

    def send_json(self, code, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        started = time.perf_counter()
        try:
            self._do_get()
        finally:
            record_request(self, started)

    def _do_get(self):
        parsed = urlparse(self.path)
        if parsed.path in ('/openapi.json', '/docs'):
            name, content_type = ('openapi.json', 'application/json; charset=utf-8') if parsed.path == '/openapi.json' else ('swagger.html', 'text/html; charset=utf-8')
            body = (Path(__file__).parent / name).read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == '/api/dashboard/simulation':
            self.send_json(200, simulation.status())
            return
        if parsed.path.startswith('/api/dashboard'):
            try:
                query = parse_qs(parsed.query)
                if parsed.path == '/api/dashboard/settings':
                    self.send_json(200, dashboard.SETTINGS)
                    return
                parts = parsed.path.strip('/').split('/')
                route_id = parts[3] if len(parts) == 4 and parts[2] == 'routes' else None
                if parsed.path != '/api/dashboard' and route_id is None:
                    self.send_json(404, {'error': 'not found'})
                    return
                direction, period = int(query.get('direction', ['0'])[0]), int(query.get('period', ['60'])[0])
                if direction not in (0,1) or period not in (30,60,180):
                    raise ValueError('Неверное направление или период')
                self.send_json(200, dashboard.snapshot(route_id=route_id, direction=direction, period=period))
            except KeyError:
                self.send_json(404, {'error': 'Маршрут не найден'})
            except ValueError as exc:
                self.send_json(400, {'error': str(exc)})
        elif self.path == "/health":
            self.send_json(200, {"status": "ok", "service": "backend", "mode": "scaffold"})
        elif self.path == "/metrics":
            lines = ['# HELP scaffold_ready Service process is running.', '# TYPE scaffold_ready gauge', 'scaffold_ready{service="backend"} 1',
                     '# HELP process_cpu_seconds_total Total user and system CPU time spent in process.', '# TYPE process_cpu_seconds_total counter',
                     f'process_cpu_seconds_total {time.process_time()}',
                     '# HELP process_resident_memory_bytes Resident memory size in bytes.', '# TYPE process_resident_memory_bytes gauge',
                     f'process_resident_memory_bytes {resident_memory_bytes()}',
                     '# HELP http_requests_total Total HTTP requests.', '# TYPE http_requests_total counter',
                     '# HELP http_request_duration_seconds HTTP request latency.', '# TYPE http_request_duration_seconds histogram']
            with METRICS_LOCK:
                requests = list(HTTP_REQUESTS.items())
                latency = list(HTTP_LATENCY_COUNTS.items())
                model_requests = list(MODEL_REQUESTS.items())
                model_latency = list(MODEL_LATENCY_COUNTS.items())
            for (method, route, status), value in requests:
                labels = f'method="{method}",route="{route}",status="{status}"'
                lines.append(f'http_requests_total{{{labels}}} {value}')
            for (method, route, status), data in latency:
                labels = f'method="{method}",route="{route}",status="{status}"'
                for index, bound in enumerate(HTTP_LATENCY_BUCKETS):
                    lines.append(f'http_request_duration_seconds_bucket{{{labels},le="{bound}"}} {data["buckets"][index]}')
                lines.append(f'http_request_duration_seconds_bucket{{{labels},le="+Inf"}} {data["count"]}')
                lines.append(f'http_request_duration_seconds_sum{{{labels}}} {data["sum"]}')
                lines.append(f'http_request_duration_seconds_count{{{labels}}} {data["count"]}')
            for (model, status), value in model_requests:
                lines.append(f'ml_client_requests_total{{model="{model}",status="{status}"}} {value}')
            for (model, status), data in model_latency:
                labels = f'model="{model}",status="{status}"'
                for index, bound in enumerate(HTTP_LATENCY_BUCKETS):
                    lines.append(f'ml_client_request_duration_seconds_bucket{{{labels},le="{bound}"}} {data["buckets"][index]}')
                lines.append(f'ml_client_request_duration_seconds_bucket{{{labels},le="+Inf"}} {data["count"]}')
                lines.append(f'ml_client_request_duration_seconds_sum{{{labels}}} {data["sum"]}')
                lines.append(f'ml_client_request_duration_seconds_count{{{labels}}} {data["count"]}')
            body = ('\n'.join(lines) + '\n').encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/predictions":
            state = simulation.status()
            self.send_json(200, {"predictions": state.get('predictions', []),
                                 "predictionCount": state.get('predictionCount', 0),
                                 "predictionTotal": state.get('predictionTotal', 0),
                                 "currentTime": state.get('currentTime'),
                                 "model": state.get('predictions', [{}])[0].get('model') if state.get('predictions') else None,
                                 "mode": "replay" if state.get('available') else "unavailable",
                                 "errors": state.get('errors', [])})
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        started = time.perf_counter()
        try:
            self._do_post()
        finally:
            record_request(self, started)

    def _do_post(self):
        if self.path == '/api/dashboard/simulation':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 1024:
                    raise ValueError('body must be 1..1024 bytes')
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError('expected JSON object')
                self.send_json(200, simulation.control(body.get('action'), body.get('speed')))
            except (ValueError, TypeError) as exc:
                self.send_json(400, {'error': str(exc)})
            except (URLError, TimeoutError, OSError) as exc:
                self.send_json(503, {'error': 'Не удалось изменить симуляцию. Проверьте доступность emulator и ingest и повторите.'})
            return
        if self.path.startswith('/api/dashboard/'):
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 65536:
                    raise ValueError('body must be 1..65536 bytes')
                body = json.loads(self.rfile.read(length))
                parts = self.path.strip('/').split('/')
                if self.path == '/api/dashboard/settings':
                    dashboard.SETTINGS = dashboard.settings_from(body)
                    self.send_json(200, dashboard.SETTINGS)
                elif len(parts) == 5 and parts[2] == 'routes' and parts[4] == 'scenario':
                    self.send_json(200, dashboard.scenario(parts[3], body))
                else:
                    self.send_json(404, {'error': 'not found'})
            except KeyError:
                self.send_json(404, {'error': 'Маршрут не найден'})
            except (ValueError, TypeError) as exc:
                self.send_json(400, {'error': str(exc)})
            return
        if self.path != "/api/predict":
            self.send_json(404, {"error": "not found"})
            return
        try:
            model_started = time.perf_counter()
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 65536:
                raise ValueError("body must be 1..65536 bytes")
            point = json.loads(self.rfile.read(length))
            if not isinstance(point, dict):
                raise ValueError("expected JSON object")
            request = Request(ML_URL + "/predict", data=json.dumps(point).encode(), headers={"Content-Type": "application/json"})
            with DIRECT_HTTP.open(request, timeout=5) as response:
                result = json.load(response)
                record_model_request(result.get('model', 'unknown'), 200, time.perf_counter() - model_started)
                self.send_json(200, result)
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json(400, {"error": str(exc)})
        except HTTPError as exc:
            record_model_request('unknown', exc.code, time.perf_counter() - model_started)
            self.send_json(exc.code, json.load(exc))
        except (URLError, TimeoutError) as exc:
            record_model_request('unknown', 503, time.perf_counter() - model_started)
            self.send_json(503, {"error": str(exc)})


if __name__ == "__main__":
    ThreadingHTTPServer((os.environ.get('HOST', '0.0.0.0'), int(os.environ.get('PORT', '8000'))), Handler).serve_forever()

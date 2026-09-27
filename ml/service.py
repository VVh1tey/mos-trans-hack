"""Serve the selected CatBoost experiment through the existing HTTP contract."""

import json
import importlib
import math
import os
import resource
import threading
import time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RUNS = Path(os.environ.get("RUNS_DIR", "/runs"))
selection = json.loads((RUNS / "selection.json").read_text(encoding="utf-8"))
run_dir = RUNS / selection["run_id"]
manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
if manifest["module"] not in {"experiments.catboost_clean", "experiments.catboost_timeseries"}:
    raise RuntimeError("Unsupported selected experiment")
experiment = importlib.import_module(manifest["module"])
MODEL = experiment.load_model(run_dir / manifest["model_file"])
METRICS_LOCK = threading.Lock()
HTTP_REQUESTS = defaultdict(int)
HTTP_LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
HTTP_LATENCY_COUNTS = defaultdict(lambda: {'buckets': [0] * len(HTTP_LATENCY_BUCKETS), 'count': 0, 'sum': 0.0, 'model_count': 0, 'model_sum': 0.0})


def resident_memory_bytes():
    try:
        with open('/proc/self/statm', encoding='ascii') as statm:
            resident_pages = int(statm.read().split()[1])
        return resident_pages * os.sysconf('SC_PAGE_SIZE')
    except (OSError, ValueError, IndexError):
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024


def record_request(handler, started):
    route = '/predict' if handler.path.startswith('/predict') else '/health'
    status = str(getattr(handler, '_status_code', 500))
    elapsed = time.perf_counter() - started
    key = (handler.command, route, status, selection['run_id'])
    with METRICS_LOCK:
        HTTP_REQUESTS[key] += 1
        data = HTTP_LATENCY_COUNTS[key]
        for index, bound in enumerate(HTTP_LATENCY_BUCKETS):
            if elapsed <= bound:
                data['buckets'][index] += 1
        data['count'] += 1
        data['sum'] += elapsed
        if route == '/predict':
            data['model_count'] += 1
            data['model_sum'] += elapsed


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
        if self.path == "/health":
            self.send_json(200, {"status": "ok", "service": "ml", "model": selection["run_id"]})
        elif self.path == "/metrics":
            lines = ['# HELP scaffold_ready Service process is running.', '# TYPE scaffold_ready gauge', 'scaffold_ready{service="ml"} 1',
                     '# HELP process_cpu_seconds_total Total user and system CPU time spent in process.', '# TYPE process_cpu_seconds_total counter',
                     f'process_cpu_seconds_total {time.process_time()}',
                     '# HELP process_resident_memory_bytes Resident memory size in bytes.', '# TYPE process_resident_memory_bytes gauge',
                     f'process_resident_memory_bytes {resident_memory_bytes()}',
                     '# HELP http_requests_total Total HTTP requests.', '# TYPE http_requests_total counter',
                     '# HELP http_request_duration_seconds HTTP request latency.', '# TYPE http_request_duration_seconds histogram',
                     '# HELP ml_model_info Loaded machine learning model.', '# TYPE ml_model_info gauge',
                     f'ml_model_info{{model="{selection["run_id"]}"}} 1']
            with METRICS_LOCK:
                requests = list(HTTP_REQUESTS.items())
                latency = list(HTTP_LATENCY_COUNTS.items())
            for (method, route, status, model), value in requests:
                labels = f'method="{method}",route="{route}",status="{status}",model="{model}"'
                lines.append(f'http_requests_total{{{labels}}} {value}')
            for (method, route, status, model), data in latency:
                labels = f'method="{method}",route="{route}",status="{status}",model="{model}"'
                for index, bound in enumerate(HTTP_LATENCY_BUCKETS):
                    lines.append(f'http_request_duration_seconds_bucket{{{labels},le="{bound}"}} {data["buckets"][index]}')
                lines.append(f'http_request_duration_seconds_bucket{{{labels},le="+Inf"}} {data["count"]}')
                lines.append(f'http_request_duration_seconds_sum{{{labels}}} {data["sum"]}')
                lines.append(f'http_request_duration_seconds_count{{{labels}}} {data["count"]}')
                if route == '/predict':
                    model_labels = f'model="{model}",status="{status}"'
                    lines.append(f'ml_inference_duration_seconds_sum{{{model_labels}}} {data["model_sum"]}')
                    lines.append(f'ml_inference_duration_seconds_count{{{model_labels}}} {data["model_count"]}')
            body = ('\n'.join(lines) + '\n').encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        started = time.perf_counter()
        try:
            self._do_post()
        finally:
            record_request(self, started)

    def _do_post(self):
        if self.path != "/predict":
            self.send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 65536:
                raise ValueError("body must be 1..65536 bytes")
            point = json.loads(self.rfile.read(length))
            if not isinstance(point, dict) or "sample_id" not in point or "cur_dev_s" not in point:
                raise ValueError("sample_id and cur_dev_s are required")
            deviation = float(point["cur_dev_s"])
            if not math.isfinite(deviation):
                raise ValueError("cur_dev_s must be finite")
            self.send_json(200, {"sample_id": point["sample_id"], "prediction": experiment.predict_one(MODEL, point), "model": selection["run_id"]})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json(400, {"error": str(exc)})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8001), Handler).serve_forever()

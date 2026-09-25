"""Temporary backend HTTP adapter. Replace with FastAPI and NDTP processing."""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


ML_URL = os.environ.get("ML_URL", "http://ml:8001")
DIRECT_HTTP = build_opener(ProxyHandler({}))


class Handler(BaseHTTPRequestHandler):
    def send_json(self, code, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"status": "ok", "service": "backend", "mode": "scaffold"})
        elif self.path == "/metrics":
            body = b'# HELP scaffold_ready Service process is running.\n# TYPE scaffold_ready gauge\nscaffold_ready{service="backend"} 1\n'
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/predictions":
            self.send_json(200, {"predictions": [], "mode": "scaffold"})
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/predict":
            self.send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 65536:
                raise ValueError("body must be 1..65536 bytes")
            point = json.loads(self.rfile.read(length))
            if not isinstance(point, dict):
                raise ValueError("expected JSON object")
            request = Request(ML_URL + "/predict", data=json.dumps(point).encode(), headers={"Content-Type": "application/json"})
            with DIRECT_HTTP.open(request, timeout=5) as response:
                self.send_json(200, json.load(response))
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json(400, {"error": str(exc)})
        except HTTPError as exc:
            self.send_json(exc.code, json.load(exc))
        except (URLError, TimeoutError) as exc:
            self.send_json(503, {"error": str(exc)})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()

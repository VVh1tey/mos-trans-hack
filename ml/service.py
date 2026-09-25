"""Small inference adapter for the baseline artifact. Replace with model serving."""

import json
import math
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


MODEL_FILE = Path(os.environ.get("MODEL_FILE", "/runs/selected.json"))


def model():
    if MODEL_FILE.is_file():
        return json.loads(MODEL_FILE.read_text(encoding="utf-8"))
    return {"name": "fallback-cur-dev", "offset_seconds": 0.0}


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
            self.send_json(200, {"status": "ok", "service": "ml", "model": model()["name"]})
        elif self.path == "/metrics":
            body = b'# HELP scaffold_ready Service process is running.\n# TYPE scaffold_ready gauge\nscaffold_ready{service="ml"} 1\n'
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
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
            current = model()
            self.send_json(200, {"sample_id": point["sample_id"], "prediction": deviation + current["offset_seconds"], "model": current["name"]})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json(400, {"error": str(exc)})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8001), Handler).serve_forever()

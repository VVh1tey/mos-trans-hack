"""Serve the selected CatBoost experiment through the existing HTTP contract."""

import json
import importlib
import math
import os
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
            self.send_json(200, {"status": "ok", "service": "ml", "model": selection["run_id"]})
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
            self.send_json(200, {"sample_id": point["sample_id"], "prediction": experiment.predict_one(MODEL, point), "model": selection["run_id"]})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json(400, {"error": str(exc)})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8001), Handler).serve_forever()

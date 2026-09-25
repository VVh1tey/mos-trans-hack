"""Explicitly select one compatible JSON model for the online scaffold."""

import json
import os
import re
import sys
from pathlib import Path


if len(sys.argv) != 2 or not re.fullmatch(r"[A-Za-z0-9_-]+", sys.argv[1]):
    raise SystemExit("Usage: python select.py <run_id>")
runs = Path(os.environ.get("RUNS_DIR", "/runs"))
run_id = sys.argv[1]
directory = runs / run_id
manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
model_file = directory / manifest["model_file"]
model = json.loads(model_file.read_text(encoding="utf-8"))
if not isinstance(model, dict) or not {"name", "offset_seconds"} <= model.keys():
    raise SystemExit("This model needs a matching online adapter; only the JSON baseline schema is supported now")
temporary = runs / "selected.json.tmp"
temporary.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
temporary.replace(runs / "selected.json")
(runs / "selection.json").write_text(json.dumps({"run_id": run_id, "model_file": manifest["model_file"]}, indent=2) + "\n", encoding="utf-8")
print(f"Selected {run_id}: {model['name']}")

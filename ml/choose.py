"""Select a trained CatBoost experiment for online inference."""

import json
import os
import re
import sys
from pathlib import Path


if len(sys.argv) != 2 or not re.fullmatch(r"[A-Za-z0-9_-]+", sys.argv[1]):
    raise SystemExit("Usage: python choose.py <run_id>")
runs = Path(os.environ.get("RUNS_DIR", "/runs"))
run_id = sys.argv[1]
directory = runs / run_id
manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
model_file = directory / manifest["model_file"]
if manifest["module"] not in {"experiments.catboost_clean", "experiments.catboost_timeseries"}:
    raise SystemExit("Select a supported CatBoost experiment")
if not model_file.is_file():
    raise SystemExit(f"Missing model: {model_file}")
(runs / "selection.json").write_text(json.dumps({"run_id": run_id, "model_file": manifest["model_file"], "module": manifest["module"]}, indent=2) + "\n", encoding="utf-8")
print(f"Selected {run_id}: CatBoost")

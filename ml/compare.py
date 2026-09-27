"""Regenerate a sortable CSV view from immutable run directories."""

import csv
import json
import os
from pathlib import Path


runs = Path(os.environ.get("RUNS_DIR", "/runs"))
rows = []
for directory in runs.iterdir():
    if not directory.is_dir():
        continue
    manifest_path = directory / "manifest.json"
    metrics_path = directory / "metrics.json"
    if not manifest_path.is_file() or not metrics_path.is_file():
        continue
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    rows.append({key: value for key, value in {
        "run_id": manifest["run_id"],
        "model": manifest["module"],
        "feature_set": manifest["feature_set"],
        "git_commit": manifest["git_commit"],
        "dataset_fingerprint": manifest["dataset_fingerprint"],
        "evaluation_protocol": manifest.get("evaluation_protocol", "original_test"),
        "test_mae_seconds": metrics["test_mae_seconds"],
        "model_file": manifest["model_file"],
    }.items()})
rows.sort(key=lambda row: (row["dataset_fingerprint"], row["evaluation_protocol"], float(row["test_mae_seconds"])))
fields = ["run_id", "model", "feature_set", "git_commit", "dataset_fingerprint", "evaluation_protocol", "test_mae_seconds", "model_file"]
runs.mkdir(parents=True, exist_ok=True)
temporary = runs / "index.csv.tmp"
with temporary.open("w", encoding="utf-8", newline="") as output:
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
temporary.replace(runs / "index.csv")
for row in rows:
    print(f'{row["test_mae_seconds"]:8.3f} s  {row["model"]:<28} {row["run_id"]}  protocol={row["evaluation_protocol"]}  data={row["dataset_fingerprint"][:10]}')

"""Median residual minimizes MAE for prediction = cur_dev_s + offset."""

import json
from statistics import median


FEATURE_SET = "cur_dev_s"


def fit(rows, dataset_root):
    return {"name": "baseline-residual-median", "offset_seconds": median(float(row["target_delay_s"]) - float(row["cur_dev_s"] or 0) for row in rows)}


def predict(model, rows, dataset_root, split):
    return [float(row["cur_dev_s"] or 0) + model["offset_seconds"] for row in rows]


def save_model(model, directory):
    path = directory / "baseline.json"
    path.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
    return path

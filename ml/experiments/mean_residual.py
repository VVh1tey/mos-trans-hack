"""Second simple experiment to demonstrate run comparison."""

import json
from statistics import mean


FEATURE_SET = "cur_dev_s"


def fit(rows, dataset_root):
    return {"name": "mean-residual", "offset_seconds": mean(float(row["target_delay_s"]) - float(row["cur_dev_s"] or 0) for row in rows)}


def predict(model, rows, dataset_root, split):
    return [float(row["cur_dev_s"] or 0) + model["offset_seconds"] for row in rows]


def save_model(model, directory):
    path = directory / "mean_residual.json"
    path.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
    return path

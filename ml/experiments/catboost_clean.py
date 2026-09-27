"""Plain CatBoost on cur_dev_s, with vehicle-disjoint training data."""

import csv
import json
import math
import os
from pathlib import Path
import sys

from catboost import CatBoostRegressor


FEATURE_SET = "cur_dev_s; train excludes test and validate tr_id"


def _vehicles(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        return {row["tr_id"] for row in csv.DictReader(source)}


def _features(rows):
    return [[float(row["cur_dev_s"] or 0)] for row in rows]


def fit(rows, dataset_root):
    root = Path(dataset_root)
    held_out = _vehicles(root / "labels/labels_test.csv") | _vehicles(root / "validate/points.csv")
    clean = [row for row in rows if row["tr_id"] not in held_out]
    if not clean:
        raise ValueError("No train vehicles remain after excluding test and validate vehicles")
    print(f"Leakage filter: {len(rows)} -> {len(clean)} train rows; excluded {len(rows) - len(clean)} rows", flush=True)
    model = CatBoostRegressor(verbose=False)
    model.fit(_features(clean), [float(row["target_delay_s"]) for row in clean])
    model.clean_train_rows = len(clean)
    return model


def predict(model, rows, dataset_root, split):
    return model.predict(_features(rows)).tolist()


def predict_one(model, point):
    return float(model.predict(_features([point]))[0])


def save_model(model, directory):
    path = directory / "catboost.cbm"
    model.save_model(str(path))
    return path


def load_model(path):
    model = CatBoostRegressor()
    model.load_model(str(path))
    return model


def make_submission(dataset_root, runs_root, output_path):
    dataset_root = Path(dataset_root)
    runs_root = Path(runs_root)
    output_path = Path(output_path)
    selection = json.loads((runs_root / "selection.json").read_text(encoding="utf-8"))
    run_dir = runs_root / selection["run_id"]
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest["module"] != "experiments.catboost_clean" or selection["model_file"] != manifest["model_file"]:
        raise ValueError("Selected run does not belong to this experiment")
    with (dataset_root / "validate/points.csv").open(encoding="utf-8-sig", newline="") as source:
        points = list(csv.DictReader(source))
    with (dataset_root / "sample_submission.csv").open(encoding="utf-8-sig", newline="") as source:
        template = list(csv.DictReader(source, delimiter=";"))
    ids = [point["sample_id"] for point in points]
    template_ids = [row["sample_id"] for row in template]
    if not ids or len(ids) != len(set(ids)) or len(template_ids) != len(set(template_ids)) or set(ids) != set(template_ids):
        raise ValueError("Validate IDs do not match the submission template")
    predictions = predict(load_model(run_dir / manifest["model_file"]), points, dataset_root, "validate")
    values = dict(zip(ids, predictions))
    if len(predictions) != len(points) or not all(math.isfinite(value) for value in predictions):
        raise ValueError("Invalid predictions")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target, delimiter=";")
        writer.writerow(["sample_id", "prediction"])
        writer.writerows((sample_id, values[sample_id]) for sample_id in template_ids)
    print(f"Saved {len(points)} predictions to {output_path} from run {selection['run_id']}")


if __name__ == "__main__":
    if sys.argv[1:] != ["submit"]:
        raise SystemExit("Usage: python -m experiments.catboost_clean submit")
    make_submission(
        os.environ.get("DATASET_DIR", "/dataset"),
        os.environ.get("RUNS_DIR", "/runs"),
        os.environ.get("SUBMISSION_FILE", "/outputs/submission.csv"),
    )

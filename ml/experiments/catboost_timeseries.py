"""CatBoost on both labeled files, with temporal evaluation and repeat removal."""

import csv
from datetime import datetime, timedelta
import json
import math
import os
from pathlib import Path
import sys

from catboost import CatBoostRegressor


FEATURE_SET = "cur_dev_s; adjacent repeats removed; chronological folds"
EMBARGO = timedelta(minutes=15)


def _time(row, field="T"):
    return datetime.fromisoformat(row[field][:19])


def _features(rows):
    return [[float(row["cur_dev_s"] or 0)] for row in rows]


def _clean(rows):
    """Keep the first point in a short run with the same observed state and label."""
    result = []
    previous = {}
    seen_ids = set()
    for row in sorted(rows, key=lambda r: (_time(r), r["tr_id"], r["sample_id"])):
        if row["sample_id"] in seen_ids:
            continue
        seen_ids.add(row["sample_id"])
        earlier = previous.get(row["tr_id"])
        if earlier is not None and (
            _time(row) - _time(earlier) <= timedelta(minutes=5)
            and row["cur_dev_s"] == earlier["cur_dev_s"]
            and row["target_delay_s"] == earlier["target_delay_s"]
        ):
            continue
        previous[row["tr_id"]] = row
        result.append(row)
    return result


def _fit(rows):
    model = CatBoostRegressor(verbose=False)
    model.fit(_features(rows), [float(row["target_delay_s"]) for row in rows])
    return model


def _mae(model, rows):
    predictions = predict(model, rows, None, "evaluation")
    return sum(abs(float(row["target_delay_s"]) - value) for row, value in zip(rows, predictions)) / len(rows)


def _past(rows, cutoff):
    """Training labels must have resolved before the next window begins."""
    return [row for row in rows if _time(row) < cutoff - EMBARGO and _time(row, "target_time_begin") <= cutoff]


def _windows(source):
    times = sorted({_time(row) for row in source})
    if len(times) < 20:
        raise ValueError("Too few distinct timestamps for chronological validation")
    val_start = times[int(len(times) * 0.6)]
    test_start = times[int(len(times) * 0.8)]
    development_source = _past(source, val_start)
    development = _clean(development_source)
    validation = _clean([row for row in source if val_start <= _time(row) < test_start - EMBARGO])
    test = _clean([row for row in source if _time(row) >= test_start])
    if not development or not validation or not test:
        raise ValueError("Empty chronological train, validation or test split")
    return development_source, development, validation, test, val_start, test_start


def run(train_rows, test_rows, dataset_root):
    source = train_rows + test_rows
    combined = _clean(source)
    development_source, development, validation, test, val_start, test_start = _windows(source)

    dev_times = sorted({_time(row) for row in development_source})
    folds = []
    for part in (1, 2, 3):
        start = dev_times[int(len(dev_times) * part / 4)]
        stop = dev_times[int(len(dev_times) * (part + 1) / 4)] if part < 3 else val_start
        fold_train = _clean(_past(development_source, start))
        fold_valid = _clean([row for row in development_source if start <= _time(row) < stop - EMBARGO])
        if not fold_train or not fold_valid:
            raise ValueError("Empty chronological CV fold")
        folds.append({
            "train_rows": len(fold_train),
            "validation_rows": len(fold_valid),
            "train_end_before": start.isoformat(sep=" "),
            "validation_end_before": stop.isoformat(sep=" "),
            "mae_seconds": _mae(_fit(fold_train), fold_valid),
        })

    holdout_model = _fit(development)
    metrics = {
        "evaluation_protocol": "combined_train_test_chronological_60_20_20_embargo_15m",
        "source_train_rows": len(train_rows),
        "source_test_rows": len(test_rows),
        "duplicate_rows_removed": len(train_rows) + len(test_rows) - len(combined),
        "clean_rows": len(combined),
        "cv_folds": folds,
        "cv_mean_mae_seconds": sum(fold["mae_seconds"] for fold in folds) / len(folds),
        "holdout_train_rows": len(development),
        "validation_rows": len(validation),
        "validation_start": val_start.isoformat(sep=" "),
        "validation_mae_seconds": _mae(holdout_model, validation),
        "test_rows": len(test),
        "test_start": test_start.isoformat(sep=" "),
        "test_mae_seconds": _mae(holdout_model, test),
        "final_train_rows": len(combined),
    }
    print(json.dumps(metrics, ensure_ascii=False), flush=True)
    return _fit(combined), metrics


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


def compare_first(dataset_root, runs_root, run_id):
    dataset_root = Path(dataset_root)
    runs_root = Path(runs_root)
    with (dataset_root / "labels/labels_train.csv").open(encoding="utf-8-sig", newline="") as source:
        original_train = list(csv.DictReader(source))
    with (dataset_root / "labels/labels_test.csv").open(encoding="utf-8-sig", newline="") as source:
        original_test = list(csv.DictReader(source))
    with (dataset_root / "validate/points.csv").open(encoding="utf-8-sig", newline="") as source:
        hidden_validate = list(csv.DictReader(source))
    held_vehicles = {row["tr_id"] for row in original_test + hidden_validate}
    first_train_ids = {row["sample_id"] for row in original_train if row["tr_id"] not in held_vehicles}
    _, development, validation, test, _, _ = _windows(original_train + original_test)
    manifest = json.loads((runs_root / run_id / "manifest.json").read_text(encoding="utf-8"))
    if manifest["module"] != "experiments.catboost_clean":
        raise ValueError("Expected a run from experiments.catboost_clean")
    first_model = load_model(runs_root / run_id / manifest["model_file"])
    second_holdout_model = _fit(development)
    result = {"first_run_id": run_id, "warning": "First model trained on some rows in these windows; full-window MAE is contaminated"}
    for name, rows in (("validation", validation), ("test", test)):
        unseen = [row for row in rows if row["sample_id"] not in first_train_ids]
        result[name] = {
            "rows": len(rows),
            "first_train_overlap_rows": len(rows) - len(unseen),
            "first_full_mae_seconds_leaky": _mae(first_model, rows),
            "unseen_rows": len(unseen),
            "first_unseen_mae_seconds": _mae(first_model, unseen),
            "second_unseen_mae_seconds": _mae(second_holdout_model, unseen),
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def make_submission(dataset_root, runs_root, output_path, run_id=None):
    dataset_root = Path(dataset_root)
    runs_root = Path(runs_root)
    output_path = Path(output_path)
    if run_id is None:
        selection = json.loads((runs_root / "selection.json").read_text(encoding="utf-8"))
        run_id = selection["run_id"]
    run_dir = runs_root / run_id
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest["module"] != "experiments.catboost_timeseries":
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
    if len(predictions) != len(points) or not all(math.isfinite(value) for value in predictions):
        raise ValueError("Invalid predictions")
    values = dict(zip(ids, predictions))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target, delimiter=";")
        writer.writerow(["sample_id", "prediction"])
        writer.writerows((sample_id, values[sample_id]) for sample_id in template_ids)
    print(f"Saved {len(points)} predictions to {output_path} from run {run_id}")


if __name__ == "__main__":
    if len(sys.argv) in (2, 3) and sys.argv[1] == "submit":
        make_submission(
            os.environ.get("DATASET_DIR", "/dataset"),
            os.environ.get("RUNS_DIR", "/runs"),
            os.environ.get("SUBMISSION_FILE", "/outputs/submission.csv"),
            sys.argv[2] if len(sys.argv) == 3 else None,
        )
    elif len(sys.argv) == 3 and sys.argv[1] == "compare-first":
        compare_first(os.environ.get("DATASET_DIR", "/dataset"), os.environ.get("RUNS_DIR", "/runs"), sys.argv[2])
    else:
        raise SystemExit("Usage: python -m experiments.catboost_timeseries submit [run_id] | compare-first <run_id>")

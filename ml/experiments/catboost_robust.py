"""Single real-only context model with missing-feature augmentation and online API."""

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

from .catboost_context import features, read_rows

FEATURES = ["cur_dev_s", "abs_dev", "hour", "hour_sin", "hour_cos", "horizon",
            "target_lon", "target_lat", "planned_gap", "segment_m", "stops_ahead", "adjusted_stops_ahead"]
PLAN = FEATURES[6:]
CLOCK = FEATURES[2:6]
SUPPORTS_MISSING = True


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else np.nan
    except (TypeError, ValueError, OverflowError):
        return np.nan


def online_features(point):
    # Unknown fields (including targets) are ignored; IDs never enter the model.
    row = {key: number(point.get(key)) for key in FEATURES}
    row["abs_dev"] = abs(row["cur_dev_s"])
    try:
        now = pd.Timestamp(point.get("T"))
        if not pd.isna(now):
            hour = now.hour + now.minute/60 + now.second/3600
            row.update(hour=hour, hour_sin=np.sin(hour*np.pi/12), hour_cos=np.cos(hour*np.pi/12))
            target = pd.Timestamp(point.get("target_time_begin"))
            if not pd.isna(target):
                row["horizon"] = (target-now).total_seconds()
    except (ValueError, TypeError, OverflowError):
        pass
    return pd.DataFrame([row], columns=FEATURES)


def prepared(frame):
    result = frame.reindex(columns=FEATURES).astype(float).replace([np.inf, -np.inf], np.nan).copy()
    for key in FEATURES:
        result[key+"_missing"] = result[key].isna().astype(float)
    return result


def fit_frame(x, y):
    rng = np.random.default_rng(42)
    views = [x.copy()]
    for mode in ("no_plan", "only_dev", "no_dev", "random", "empty"):
        part = x.copy()
        if mode == "no_plan":
            part[PLAN] = np.nan
        elif mode == "only_dev":
            part[CLOCK+PLAN] = np.nan
        elif mode == "no_dev":
            part[["cur_dev_s", "abs_dev", "adjusted_stops_ahead"]] = np.nan
        elif mode == "random":
            part = part.mask(rng.random(part.shape) < 0.25)
            part["abs_dev"] = part.cur_dev_s.abs()
            part.loc[part.cur_dev_s.isna(), "adjusted_stops_ahead"] = np.nan
        else:
            part[:] = np.nan
        views.append(part)
    augmented = pd.concat(views, ignore_index=True)
    offsets = augmented.cur_dev_s.fillna(0).to_numpy()
    # Full data retains most weight; missingness is simulated only inside training folds.
    weights = np.repeat([1.0, 0.2, 0.2, 0.2, 0.2, 0.05], len(x))
    model = CatBoostRegressor(iterations=600, depth=4, learning_rate=0.04, loss_function="MAE",
                             l2_leaf_reg=10, random_seed=42, thread_count=4, verbose=False,
                             allow_writing_files=False)
    model.fit(prepared(augmented), np.tile(y, len(views))-offsets, sample_weight=weights)
    return model


def predict_frame(model, frame):
    return model.predict(prepared(frame)) + frame.cur_dev_s.fillna(0).to_numpy()


def predict_one(model, point):
    return float(predict_frame(model, online_features(point))[0])


def load_model(path):
    model = CatBoostRegressor()
    model.load_model(str(path))
    return model


def main():
    root = Path(os.environ.get("DATASET_DIR", "/dataset"))
    real = {r["tr_id"] for r in read_rows(root/"labels/labels_test.csv")}
    rows, frames, seen = [], [], set()
    for split in ("train", "test"):
        part = []
        for r in read_rows(root/f"labels/labels_{split}.csv"):
            if r["tr_id"] in real and r["sample_id"] not in seen:
                seen.add(r["sample_id"])
                part.append(r)
        frames.append(features(part, root, split, False))
        rows.extend(part)
    x = pd.concat(frames, ignore_index=True)[FEATURES]
    y = np.array([float(r["target_delay_s"]) for r in rows])
    groups = np.array([r["tr_id"] for r in rows])
    scenarios = {"full": x.copy(), "no_plan": x.copy(), "only_dev": x.copy(), "no_dev": x.copy(), "empty": x.copy()}
    scenarios["no_plan"][PLAN] = np.nan
    scenarios["only_dev"][CLOCK+PLAN] = np.nan
    scenarios["no_dev"][["cur_dev_s", "abs_dev", "adjusted_stops_ahead"]] = np.nan
    scenarios["empty"][:] = np.nan
    predictions = {key: np.full(len(x), np.nan) for key in scenarios}
    baseline = np.full(len(x), np.nan)
    for vehicle in sorted(real):
        train, test = groups != vehicle, groups == vehicle
        model = fit_frame(x.loc[train], y[train])
        simple = CatBoostRegressor(verbose=False, thread_count=4, random_seed=42, allow_writing_files=False)
        simple.fit(x.loc[train, ["cur_dev_s"]], y[train])
        baseline[test] = simple.predict(x.loc[test, ["cur_dev_s"]])
        for name, values in scenarios.items():
            predictions[name][test] = predict_frame(model, values.loc[test])
        print(f"Checked held-out vehicle {vehicle}", flush=True)
    metrics = dict(evaluation_protocol="real_only_leave_one_vehicle_out_with_missingness",
                   real_rows=len(rows), real_vehicles=len(real), synthetic_rows=0,
                   baseline_mae=float(np.mean(abs(baseline-y))),
                   scenario_mae={k: float(np.mean(abs(v-y))) for k,v in predictions.items()})
    model = fit_frame(x, y)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")+"-robust-final"
    directory = Path(os.environ.get("RUNS_DIR", "/runs"))/run_id
    directory.mkdir(parents=True)
    model.save_model(str(directory/"catboost.cbm"))
    manifest = dict(run_id=run_id, module="experiments.catboost_robust", model_file="catboost.cbm",
                    feature_set="context12 + missing flags; real-only; missingness augmentation",
                    evaluation_protocol=metrics["evaluation_protocol"], parameters=model.get_params(),
                    source_sha256={}, input_sha256={},
                    warning="Final model uses all real labels. Do not evaluate it on the old test/validate; use reported out-of-vehicle predictions.")
    for name in ("catboost_robust.py", "catboost_context.py"):
        content = Path(__file__).with_name(name).read_bytes()
        (directory/name).write_bytes(content)
        manifest["source_sha256"][name] = hashlib.sha256(content).hexdigest()
    for path in sorted(root.rglob("*.csv")):
        manifest["input_sha256"][str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    (directory/"manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (directory/"metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    pd.DataFrame(dict(sample_id=[r["sample_id"] for r in rows], vehicle=groups, target=y, baseline=baseline, **predictions)).to_csv(directory/"oof.csv", index=False)
    print(json.dumps(dict(run_id=run_id, **metrics)), flush=True)


if __name__ == "__main__":
    main()

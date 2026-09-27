"""Plan-only context, MAE residual learning; CLI also writes a submission."""

import csv
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

FEATURE_SET = "v1: cur_dev residual + clock + planned stop geometry; vehicle-disjoint"


def read_rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def seconds(values):
    return pd.to_datetime(values, format="mixed").to_numpy(dtype="datetime64[ns]").astype("int64") / 1e9


def distance(lon1, lat1, lon2, lat2):
    return 6371000 * 2 * np.arcsin(np.sqrt(np.clip(
        np.sin(np.radians(lat2 - lat1) / 2) ** 2
        + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2))
        * np.sin(np.radians(lon2 - lon1) / 2) ** 2, 0, 1)))


def features(rows, root, split, telemetry=False):
    root = Path(root)
    plan_path = root / split / ("schedule_plan.csv" if split == "validate" else "schedule.csv")
    # Explicit allowlist: actual arrival times and labels never enter features.
    plan = pd.read_csv(plan_path, usecols=["tt_action_item_id", "tr_id", "time_begin", "geom"], dtype={"tr_id": str, "tt_action_item_id": str})
    plan["ts"] = seconds(plan.time_begin)
    coords = plan.geom.str.extract(r"POINT\s*\(\s*([\d.-]+)\s+([\d.-]+)\s*\)").astype(float)
    plan["lon"], plan["lat"] = coords[0], coords[1]
    plans = {key: group.sort_values("ts") for key, group in plan.groupby("tr_id")}
    stops = plan.drop_duplicates("tt_action_item_id").set_index("tt_action_item_id")
    tracks = {}
    if telemetry:
        gps = pd.read_csv(root / split / "traffic.csv", usecols=["tr_id", "event_time", "location_valid", "lon", "lat", "speed"], dtype={"tr_id": str})
        gps = gps[gps.location_valid.astype(str).str.lower().eq("true") & gps.lon.notna() & gps.lat.notna()].copy()
        gps["ts"] = seconds(gps.event_time)
        tracks = {key: group.sort_values("ts").drop_duplicates("ts") for key, group in gps.groupby("tr_id")}
    output = []
    for row in rows:
        now = pd.Timestamp(row["T"]).timestamp()
        target = pd.Timestamp(row["target_time_begin"]).timestamp()
        dev = float(row["cur_dev_s"] or 0)
        hour = (now % 86400) / 3600
        f = dict(cur_dev_s=dev, abs_dev=abs(dev), hour=hour, hour_sin=np.sin(hour * np.pi / 12), hour_cos=np.cos(hour * np.pi / 12), horizon=target-now)
        schedule = plans[row["tr_id"]]
        stop = stops.loc[row["target_stop_id"]]
        times = schedule.ts.to_numpy()
        idx = np.searchsorted(times, target)
        prev = schedule.iloc[max(0, idx-1)]
        f.update(target_lon=stop.lon, target_lat=stop.lat, planned_gap=target-prev.ts,
                 segment_m=distance(prev.lon, prev.lat, stop.lon, stop.lat),
                 stops_ahead=int(((times > now) & (times <= target)).sum()),
                 adjusted_stops_ahead=int(((times > now-dev) & (times <= target)).sum()))
        if telemetry:
            # All windows end at T, including when source CSV contains later packets.
            track = tracks.get(row["tr_id"])
            f.update(gps_age=np.nan, lon=np.nan, lat=np.nan, speed=np.nan, distance_target=np.nan,
                     progress_delay=np.nan, nearest_plan_m=np.nan)
            past = None if track is None else track.iloc[:np.searchsorted(track.ts.to_numpy(), now, side="right")]
            if past is not None and len(past):
                last = past.iloc[-1]
                f.update(gps_age=now-last.ts, lon=last.lon, lat=last.lat, speed=last.speed,
                         distance_target=distance(last.lon,last.lat,stop.lon,stop.lat))
                nearby = schedule[(schedule.ts >= now-dev-1800) & (schedule.ts <= now-dev+1800)]
                if len(nearby):
                    d = distance(last.lon,last.lat,nearby.lon.to_numpy(),nearby.lat.to_numpy())
                    nearest = int(np.argmin(d))
                    f.update(progress_delay=now-nearby.iloc[nearest].ts, nearest_plan_m=d[nearest])
            for window in (60, 300, 900):
                recent = None if past is None else past[past.ts >= now-window]
                vals = dict(count=0, speed_mean=np.nan, speed_std=np.nan, stopped=np.nan, moved_m=np.nan, approach_m=np.nan)
                if recent is not None and len(recent):
                    first, last = recent.iloc[0], recent.iloc[-1]
                    vals.update(count=len(recent), speed_mean=recent.speed.mean(), speed_std=recent.speed.std(ddof=0),
                                stopped=(recent.speed.fillna(0) < 3).mean(),
                                moved_m=distance(first.lon,first.lat,last.lon,last.lat),
                                approach_m=distance(first.lon,first.lat,stop.lon,stop.lat)-distance(last.lon,last.lat,stop.lon,stop.lat))
                f.update({f"gps_{window}_{key}": value for key, value in vals.items()})
        output.append(f)
    return pd.DataFrame(output).astype(float).replace([np.inf, -np.inf], np.nan)


def fit_impl(rows, root, telemetry=False):
    held = {r["tr_id"] for r in read_rows(Path(root)/"labels/labels_test.csv") + read_rows(Path(root)/"validate/points.csv")}
    clean = [r for r in rows if r["tr_id"] not in held]
    if not clean:
        raise ValueError("No vehicle-disjoint training rows")
    x = features(clean, root, "train", telemetry)
    y = np.array([float(r["target_delay_s"]) for r in clean]) - x.cur_dev_s.to_numpy()
    model = CatBoostRegressor(iterations=int(os.environ.get("CB_ITERATIONS", "700")), depth=5,
                              learning_rate=0.04, loss_function="MAE", l2_leaf_reg=8,
                              random_seed=42, thread_count=4, verbose=200, allow_writing_files=False)
    model.fit(x, y)
    model.clean_train_rows = len(clean)
    return model


def fit(rows, dataset_root):
    return fit_impl(rows, dataset_root)


def predict_impl(model, rows, root, split, telemetry=False):
    x = features(rows, root, split, telemetry)
    return (model.predict(x) + x.cur_dev_s.to_numpy()).tolist()


def predict(model, rows, dataset_root, split):
    return predict_impl(model, rows, dataset_root, split)


def save_model(model, directory):
    path = Path(directory) / "catboost.cbm"
    model.save_model(str(path))
    return path


def main(telemetry=False):
    """Train, evaluate on original test, save model and ready-to-upload CSV."""
    from datetime import datetime, timezone
    root = Path(os.environ.get("DATASET_DIR", "/dataset"))
    name = "telemetry" if telemetry else "context"
    run_dir = Path(os.environ.get("RUNS_DIR", "/runs")) / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + name)
    run_dir.mkdir(parents=True)
    train = read_rows(root/"labels/labels_train.csv")
    test = read_rows(root/"labels/labels_test.csv")
    model = fit_impl(train, root, telemetry)
    predicted = predict_impl(model, test, root, "test", telemetry)
    mae = float(np.mean(np.abs(np.array(predicted)-[float(r["target_delay_s"]) for r in test])))
    save_model(model, run_dir)
    metrics = dict(test_mae_seconds=mae, clean_train_rows=model.clean_train_rows, test_rows=len(test), evaluation_protocol="original_test", telemetry=telemetry)
    (run_dir/"metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (run_dir/"feature_importance.json").write_text(json.dumps(dict(sorted(zip(model.feature_names_, model.feature_importances_.tolist()), key=lambda kv: -kv[1])), indent=2), encoding="utf-8")
    points = read_rows(root/"validate/points.csv")
    values = predict_impl(model, points, root, "validate", telemetry)
    mapping = dict(zip([r["sample_id"] for r in points], values))
    with (root/"sample_submission.csv").open(encoding="utf-8-sig") as source:
        ids = [r["sample_id"] for r in csv.DictReader(source, delimiter=";")]
    if len(mapping) != len(points) or len(ids) != len(set(ids)) or set(ids) != set(mapping) or not np.isfinite(values).all():
        raise ValueError("Invalid submission IDs or predictions")
    output = Path(os.environ.get("SUBMISSION_FILE", f"/outputs/submission_{name}.csv"))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as target:
        writer = csv.writer(target, delimiter=";")
        writer.writerow(["sample_id", "prediction"])
        writer.writerows((key, mapping[key]) for key in ids)
    (run_dir/"submission.csv").write_bytes(output.read_bytes())
    # Keep source and hashes with the model for reproducible standalone runs.
    inputs = {}
    for relative in ("labels/labels_train.csv", "labels/labels_test.csv", "train/traffic.csv", "train/schedule.csv", "test/traffic.csv", "test/schedule.csv"):
        inputs[relative] = hashlib.sha256((root/relative).read_bytes()).hexdigest()
    source_hashes = {}
    for filename in ("catboost_context.py", "catboost_telemetry.py"):
        content = Path(__file__).with_name(filename).read_bytes()
        (run_dir/filename).write_bytes(content)
        source_hashes[filename] = hashlib.sha256(content).hexdigest()
    manifest = dict(run_id=run_dir.name, module=f"experiments.catboost_{name}",
                    feature_set=FEATURE_SET + (" + causal GPS 1/5/15min" if telemetry else ""),
                    model_file="catboost.cbm", git_commit=os.environ.get("GIT_COMMIT", "unknown"),
                    evaluation_protocol="original_test", input_sha256=inputs,
                    dataset_fingerprint=hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest(),
                    source_sha256=source_hashes, parameters=model.get_params())
    (run_dir/"manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(dict(run_dir=str(run_dir), submission=str(output), **metrics)), flush=True)


if __name__ == "__main__":
    main()

"""Real-only leave-one-vehicle-out models and submissions, no synthetic siblings."""

import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

from .catboost_context import features, read_rows


def main():
    root = Path(os.environ.get("DATASET_DIR", "/dataset"))
    out = Path(os.environ.get("OUTPUTS_DIR", "/outputs"))
    directory = Path(os.environ.get("RUNS_DIR", "/runs")) / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-real-only")
    directory.mkdir(parents=True)
    out.mkdir(parents=True, exist_ok=True)
    # In this supplied dataset, real vehicles are enumerated by the real-only test.
    # Do not infer real/synthetic status solely from an arbitrary numeric threshold.
    test = read_rows(root / "labels/labels_test.csv")
    real_ids = {r["tr_id"] for r in test}
    points = read_rows(root / "validate/points.csv")
    assert {r["tr_id"] for r in points} <= real_ids
    rows, frames, seen = [], [], {}
    for split in ("train", "test"):
        chosen = []
        for r in read_rows(root / f"labels/labels_{split}.csv"):
            if r["tr_id"] not in real_ids:
                continue
            if r["sample_id"] in seen:
                assert seen[r["sample_id"]] == r, "Conflicting duplicate sample"
                continue
            seen[r["sample_id"]] = r
            chosen.append(r)
        frames.append(features(chosen, root, split, telemetry=True))
        rows.extend(chosen)
    x = pd.concat(frames, ignore_index=True)
    xp = features(points, root, "validate", telemetry=True)
    context_cols = features(points[:1], root, "validate", telemetry=False).columns.tolist()
    groups = np.array([r["tr_id"] for r in rows])
    pgroups = np.array([r["tr_id"] for r in points])
    y = np.array([float(r["target_delay_s"]) for r in rows])
    dev = x.cur_dev_s.to_numpy()
    pdev = xp.cur_dev_s.to_numpy()
    variants = {"baseline": ["cur_dev_s"], "context": context_cols, "telemetry": x.columns.tolist()}
    oof = {name: np.full(len(rows), np.nan) for name in variants}
    predictions = {name: np.full(len(points), np.nan) for name in variants}
    folds = []
    for held in sorted(real_ids):
        train_mask, valid_mask, predict_mask = groups != held, groups == held, pgroups == held
        trained_ids = sorted(set(groups[train_mask]))
        assert held not in trained_ids
        fold = dict(held_vehicle=held, train_vehicles=trained_ids, train_rows=int(train_mask.sum()),
                    validation_rows=int(valid_mask.sum()), submission_rows=int(predict_mask.sum()))
        for name, columns in variants.items():
            if name == "baseline":
                model = CatBoostRegressor(verbose=False, random_seed=42, thread_count=4, allow_writing_files=False)
                target = y
            else:
                model = CatBoostRegressor(iterations=500, depth=4, learning_rate=0.04, loss_function="MAE",
                                          l2_leaf_reg=10, random_seed=42, thread_count=4,
                                          verbose=False, allow_writing_files=False)
                target = y - dev
            model.fit(x.loc[train_mask, columns], target[train_mask])
            values = model.predict(x.loc[valid_mask, columns])
            if name != "baseline":
                values += dev[valid_mask]
            oof[name][valid_mask] = values
            fold[name + "_mae"] = float(np.mean(np.abs(values-y[valid_mask])))
            model_path = directory / f"{name}_exclude_{held}.cbm"
            model.save_model(str(model_path))
            if predict_mask.any():
                # Verify the actual serialized model used for submission.
                loaded = CatBoostRegressor()
                loaded.load_model(str(model_path))
                values = loaded.predict(xp.loc[predict_mask, columns])
                if name != "baseline":
                    values += pdev[predict_mask]
                predictions[name][predict_mask] = values
        folds.append(fold)
        print(json.dumps(fold), flush=True)
    with (root / "sample_submission.csv").open(encoding="utf-8-sig") as source:
        ids = [r["sample_id"] for r in csv.DictReader(source, delimiter=";")]
    assert len(ids) == len(set(ids)) == len(points)
    metrics = dict(evaluation_protocol="real_only_leave_one_vehicle_out", rows=len(rows),
                   real_vehicles=len(real_ids), synthetic_training_rows=0,
                   persistence_mae=float(np.mean(np.abs(dev-y))), folds=folds)
    for name in variants:
        assert np.isfinite(oof[name]).all() and np.isfinite(predictions[name]).all()
        metrics[name + "_oof_mae"] = float(np.mean(np.abs(oof[name]-y)))
        metrics[name + "_vehicle_mean_mae"] = float(np.mean([f[name + "_mae"] for f in folds]))
        values = dict(zip([r["sample_id"] for r in points], predictions[name]))
        assert set(values) == set(ids)
        path = out / f"submission_real_only_{name}.csv"
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.writer(target, delimiter=";")
            writer.writerow(["sample_id", "prediction"])
            writer.writerows((sid, values[sid]) for sid in ids)
        (directory / path.name).write_bytes(path.read_bytes())
    pd.DataFrame(dict(sample_id=[r["sample_id"] for r in rows], tr_id=groups,
                      target=y, **oof)).to_csv(directory / "oof.csv", index=False)
    (directory / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    # Separate bundle format: online choose.py does not support a per-vehicle router.
    manifest = dict(kind="real_only_vehicle_exclusion_bundle", run_id=directory.name,
                    evaluation_protocol=metrics["evaluation_protocol"], folds=folds,
                    feature_columns=variants, input_sha256={}, source_sha256={},
                    note="Each prediction excludes its entire real vehicle. Train and test labels are pooled; no chronological generalization claim.")
    for path in sorted(root.rglob("*.csv")):
        manifest["input_sha256"][str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ("catboost_real_only.py", "catboost_context.py"):
        content = Path(__file__).with_name(name).read_bytes()
        (directory / name).write_bytes(content)
        manifest["source_sha256"][name] = hashlib.sha256(content).hexdigest()
    (directory / "bundle.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(dict(run_dir=str(directory), **{k: v for k, v in metrics.items() if k != "folds"})), flush=True)


if __name__ == "__main__":
    main()

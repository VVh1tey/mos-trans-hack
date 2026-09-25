"""Run one experiment and save an immutable, portable result directory."""

import csv
import hashlib
import importlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


DATASET = Path(os.environ.get("DATASET_DIR", "/dataset"))
RUNS = Path(os.environ.get("RUNS_DIR", "/runs"))
MODULE = os.environ.get("TRAIN_MODULE", "experiments.baseline")
RUN_NAME = os.environ.get("TRAIN_RUN_NAME") or MODULE.rsplit(".", 1)[-1]


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_split(split):
    path = DATASET / "labels" / f"labels_{split}.csv"
    if not path.is_file():
        raise SystemExit(f"Missing {path}; unpack the challenge dataset into ./dataset")
    with path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    if not rows:
        raise SystemExit(f"Empty labels: {path}")
    return rows


if not MODULE.startswith("experiments.") or MODULE.count(".") != 1:
    raise SystemExit("TRAIN_MODULE must name a module in ml/experiments")

train = load_split("train")
test = load_split("test")
experiment = importlib.import_module(MODULE)
model = experiment.fit(train, DATASET)
predictions = experiment.predict(model, test, DATASET, "test")
if len(predictions) != len(test):
    raise SystemExit("Experiment returned the wrong number of predictions")
mae = sum(abs(float(row["target_delay_s"]) - prediction) for row, prediction in zip(test, predictions)) / len(test)

run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
run_dir = RUNS / run_id
run_dir.mkdir(parents=True, exist_ok=False)
model_path = experiment.save_model(model, run_dir)
model_path = Path(model_path).resolve()
if not model_path.is_file() or model_path.parent != run_dir.resolve():
    raise SystemExit("save_model must return a file directly inside the run directory")

files = {}
for relative in (
    "labels/labels_train.csv", "labels/labels_test.csv",
    "train/traffic.csv", "train/schedule.csv",
    "test/traffic.csv", "test/schedule.csv",
):
    path = DATASET / relative
    if path.is_file():
        files[relative] = sha256_file(path)
fingerprint = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
metrics = {"train_rows": len(train), "test_rows": len(test), "test_mae_seconds": mae}
manifest = {
    "run_id": run_id,
    "run_name": RUN_NAME,
    "created_at_utc": datetime.now(timezone.utc).isoformat(),
    "module": MODULE,
    "feature_set": getattr(experiment, "FEATURE_SET", "unspecified"),
    "git_commit": os.environ.get("GIT_COMMIT", "unknown"),
    "dataset_fingerprint": fingerprint,
    "input_sha256": files,
    "module_sha256": sha256_file(Path(experiment.__file__)),
    "runner_sha256": sha256_file(Path(__file__)),
    "model_file": model_path.name,
}
(run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
(run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"run_id": run_id, "module": MODULE, **metrics}, ensure_ascii=False), flush=True)

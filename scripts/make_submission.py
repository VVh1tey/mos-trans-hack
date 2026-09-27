"""Produce validate predictions using the selected serialized robust run."""
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ml'))
from experiments.catboost_context import features, read_rows
from experiments.catboost_robust import load_model, predict_frame


def main():
    selection = json.loads((ROOT / 'runs/selection.json').read_text())
    if selection['module'] != 'experiments.catboost_robust':
        raise ValueError('This exporter requires catboost_robust')
    directory = ROOT / 'runs' / selection['run_id']
    model_path = directory / selection['model_file']
    rows = read_rows(ROOT / 'dataset/validate/points.csv')
    ids = [r['sample_id'] for r in rows]
    assert rows and len(ids) == len(set(ids)), 'Empty or duplicate validate IDs'
    values = predict_frame(load_model(model_path), features(rows, ROOT / 'dataset', 'validate'))
    assert len(values) == len(rows) and all(math.isfinite(float(v)) for v in values)
    out = ROOT / 'submission'
    out.mkdir(exist_ok=True)
    path = out / 'submission_catboost_robust.csv'
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream, delimiter=';', lineterminator='\n')
        writer.writerow(['sample_id', 'prediction'])
        writer.writerows((key, float(value)) for key, value in zip(ids, values))
    metadata = dict(run_id=selection['run_id'], rows=len(rows), delimiter=';',
                    model_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),
                    csv_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    platform_submitted=False, platform_score=None)
    (out / 'manifest.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(metadata))


if __name__ == '__main__':
    main()

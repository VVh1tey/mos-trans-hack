"""Audit synthetic source overlap in the supplied challenge dataset (stdlib only)."""

import collections
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import statistics


ROOT = Path(__file__).resolve().parents[1]


def read(relative):
    with (ROOT / "dataset" / relative).open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def stamp(value):
    return datetime.fromisoformat(value[:26])


def main():
    train = read("labels/labels_train.csv")
    test = read("labels/labels_test.csv")
    validate = read("validate/points.csv")
    held = {r["tr_id"] for r in test + validate}
    clean = [r for r in train if r["tr_id"] not in held]
    groups = collections.defaultdict(list)
    for row in read("train/schedule.csv"):
        groups[row["tr_id"]].append(row)
    groups = {k: sorted(v, key=lambda r: r["time_begin"]) for k, v in groups.items()}
    pairs = []
    for vehicle in sorted({r["tr_id"] for r in clean}):
        synthetic = groups[vehicle]
        matches = []
        for original_id in sorted(held & groups.keys()):
            original = groups[original_id]
            if len(original) != len(synthetic):
                continue
            if any(a["geom"] != b["geom"] for a, b in zip(synthetic, original)):
                continue
            shifts = [(stamp(a["time_begin"]) - stamp(b["time_begin"])).total_seconds()
                      for a, b in zip(synthetic, original)]
            if max(shifts) - min(shifts) > 0.001:
                continue
            differences = [abs((stamp(a["time_fact_begin"]) - stamp(a["time_begin"])).total_seconds()
                               - (stamp(b["time_fact_begin"]) - stamp(b["time_begin"])).total_seconds())
                           for a, b in zip(synthetic, original)
                           if a["time_fact_begin"] and b["time_fact_begin"]]
            matches.append(dict(original_vehicle=original_id, stops=len(synthetic),
                                plan_shift_seconds=shifts[0],
                                delay_difference_mae_seconds=statistics.mean(differences),
                                original_in_validate=original_id in {r["tr_id"] for r in validate}))
        pairs.append(dict(training_vehicle=vehicle, matches=matches))
    artifacts = {}
    for name, run in (("context", "20260927T204822377080Z-context"),
                      ("telemetry", "20260927T204824991102Z-telemetry")):
        directory = ROOT / "runs" / run
        manifest = json.loads((directory / "manifest.json").read_text())
        artifacts[name] = dict(
            submission_matches_saved_run=(ROOT / "outputs" / f"submission_{name}.csv").read_bytes()
            == (directory / "submission.csv").read_bytes(),
            current_sources_match_saved_run=all(
                hashlib.sha256((ROOT / "ml/experiments" / file).read_bytes()).hexdigest() == digest
                for file, digest in manifest["source_sha256"].items()),
        )
    result = dict(
        train_rows_before_filter=len(train), train_rows_after_filter=len(clean),
        held_vehicle_overlap=len({r["tr_id"] for r in clean} & held),
        held_sample_overlap=len({r["sample_id"] for r in clean} & {r["sample_id"] for r in test + validate}),
        training_vehicles=len(pairs), vehicles_matching_held_out_schedule=sum(bool(p["matches"]) for p in pairs),
        training_rows_remaining_after_source_group_exclusion=sum(
            r["tr_id"] not in {p["training_vehicle"] for p in pairs if p["matches"]} for r in clean),
        pairs=pairs, artifacts=artifacts,
        conclusion="Vehicle ID exclusion does not remove shifted synthetic copies of held-out vehicle schedules. Scores are not independent source-group validation.",
    )
    path = ROOT / "outputs/leakage_audit.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

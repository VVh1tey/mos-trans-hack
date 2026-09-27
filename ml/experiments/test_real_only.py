"""Regression checks for timestamp units, causal features, and saved fold routing."""

import json
import os
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from .catboost_context import features, read_rows, seconds


class LeakageChecks(unittest.TestCase):
    def test_timestamp_precision(self):
        for value in ("2026-01-06 12:30:00", "2026-01-06 12:30:00.123456", "2026-01-06 12:30:00.123456000"):
            self.assertAlmostEqual(seconds(pd.Series([value]))[0], pd.Timestamp(value).timestamp(), places=5)

    def test_future_packets_and_actual_arrivals_are_unused(self):
        dataset = Path(os.environ.get("DATASET_DIR", "/dataset"))
        points = read_rows(dataset / "labels/labels_test.csv")
        gps = pd.read_csv(dataset / "test/traffic.csv")
        plan = pd.read_csv(dataset / "test/schedule.csv")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "test").mkdir()
            for row in (points[40], points[len(points)//2], points[-1]):
                plan.to_csv(root / "test/schedule.csv", index=False)
                gps.to_csv(root / "test/traffic.csv", index=False)
                before = features([row], root, "test", telemetry=True)
                altered = gps.copy()
                future = pd.to_datetime(altered.event_time, format="mixed") > pd.Timestamp(row["T"])
                self.assertTrue(future.any())
                altered.loc[future, ["lon", "lat", "speed"]] = 999
                altered.to_csv(root / "test/traffic.csv", index=False)
                changed_plan = plan.copy()
                changed_plan["time_fact_begin"] = "2099-01-01"
                changed_plan.to_csv(root / "test/schedule.csv", index=False)
                poisoned = dict(row, target_delay_s="999999", target_class="poison")
                after = features([poisoned], root, "test", telemetry=True)
                pd.testing.assert_frame_equal(before, after)

    def test_bundle_excludes_held_vehicle_and_has_complete_submissions(self):
        directory = Path(os.environ["AUDIT_RUN_DIR"])
        bundle = json.loads((directory / "bundle.json").read_text())
        dataset = Path(os.environ.get("DATASET_DIR", "/dataset"))
        real = {r["tr_id"] for r in read_rows(dataset / "labels/labels_test.csv")}
        for fold in bundle["folds"]:
            self.assertEqual(set(fold["train_vehicles"]), real - {fold["held_vehicle"]})
            self.assertEqual(len(fold["train_vehicles"]), 12)
        expected = {r["sample_id"] for r in read_rows(dataset / "validate/points.csv")}
        for name in bundle["feature_columns"]:
            data = pd.read_csv(directory / f"submission_real_only_{name}.csv", sep=";")
            self.assertEqual(set(data.sample_id), expected)
            self.assertTrue(data.sample_id.is_unique)
            self.assertTrue(np.isfinite(data.prediction).all())


if __name__ == "__main__":
    unittest.main()

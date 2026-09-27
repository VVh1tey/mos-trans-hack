"""Exercise the final serialized model and HTTP service with incomplete inputs."""

import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.request import Request, urlopen

import numpy as np

from .catboost_context import features, read_rows
from .catboost_robust import FEATURES, load_model, online_features, predict_one, predict_frame


class RobustModelChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = Path(os.environ["AUDIT_RUN_DIR"])
        cls.model = load_model(cls.directory/"catboost.cbm")

    def test_missing_invalid_and_random_inputs(self):
        cases = [{}, {"cur_dev_s": 120}, {"cur_dev_s": None},
                 {k: "bad" for k in FEATURES}, {k: float("inf") for k in FEATURES},
                 {"T": "broken", "target_time_begin": "broken"}]
        rng = np.random.default_rng(4)
        for _ in range(100):
            cases.append({k: float(rng.normal()) if rng.random() > .5 else None for k in FEATURES})
        for point in cases:
            self.assertTrue(math.isfinite(predict_one(self.model, point)))

    def test_offline_online_features_match(self):
        root = Path(os.environ.get("DATASET_DIR", "/dataset"))
        rows = read_rows(root/"labels/labels_test.csv")[:20]
        frame = features(rows, root, "test", False)
        for i, point in enumerate(rows):
            request = dict(frame.iloc[i].to_dict(), T=point["T"], target_time_begin=point["target_time_begin"])
            np.testing.assert_allclose(online_features(request)[FEATURES], frame.iloc[[i]][FEATURES], equal_nan=True)
            self.assertAlmostEqual(predict_one(self.model, request), float(predict_frame(self.model, frame.iloc[[i]])[0]))

    def test_http_partial_requests(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/self.directory.name).symlink_to(self.directory, target_is_directory=True)
            (root/"selection.json").write_text(json.dumps(dict(run_id=self.directory.name)))
            process = subprocess.Popen([sys.executable, "/app/service.py"], env=dict(os.environ, RUNS_DIR=folder),
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                for _ in range(100):
                    try:
                        with urlopen("http://localhost:8001/health", timeout=.5):
                            break
                    except OSError:
                        time.sleep(.05)
                for body in ({"sample_id": "empty"}, {"sample_id": "null", "cur_dev_s": None},
                             {"sample_id": "bad", "cur_dev_s": "broken"}, {"sample_id": "dev", "cur_dev_s": 120}):
                    request = Request("http://localhost:8001/predict", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
                    with urlopen(request, timeout=5) as response:
                        result = json.load(response)
                    self.assertEqual(result["sample_id"], body["sample_id"])
                    self.assertTrue(math.isfinite(result["prediction"]))
            finally:
                process.terminate()
                process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()

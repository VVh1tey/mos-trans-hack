"""GPS history and schedule progress, strictly as of prediction time T."""

from .catboost_context import fit_impl, predict_impl, save_model, main

FEATURE_SET = "v1: MAE residual + plan context + causal GPS 1/5/15min + schedule progress"


def fit(rows, dataset_root):
    return fit_impl(rows, dataset_root, telemetry=True)


def predict(model, rows, dataset_root, split):
    return predict_impl(model, rows, dataset_root, split, telemetry=True)


if __name__ == "__main__":
    main(telemetry=True)

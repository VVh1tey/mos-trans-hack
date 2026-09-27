# Online models and remaining work

## What is connected

- The historical replay sends the test telemetry through the same NDTP decoder and ingest receiver used by the emulator.
- During historical replay, each new packet can trigger a CatBoost call when that vehicle has a planned stop strictly more than 10 and at most 15 minutes ahead. The same vehicle/stop is refreshed at most once every 120 virtual seconds. The feature is the latest delay already observed by event time, or zero before the first observed arrival. Separate labeled points are also predicted for MAE evaluation; future labels are exposed only after their reveal time. The MAE card uses only those labeled points, not the additional stream forecasts.
- `runs/selection.json` selects the CatBoost artifact loaded by the ML service. Keep the selected run directory and its manifest alongside that pointer when moving the repository.
- Live replay predictions are visible in the replay panel, and the reported MAE is calculated only for labels whose actual arrival has occurred in virtual replay time.
- What-if currently uses a transparent illustrative headway formula. It is not served by the CatBoost delay model: the targets and features are different.

## Model inventory

| Capability | Current state | Needed next |
| --- | --- | --- |
| Stop delay prediction | CatBoost trained on `cur_dev_s`; used by replay inference | Re-evaluate on the newest complete labeled dataset; add route, stop, time-of-day and recent vehicle history only when those features are available consistently at training and inference time |
| Delay risk probability | Demo value in the dashboard | Train and calibrate a classifier on an explicit delay threshold; report calibration and precision/recall by route and forecast horizon |
| Headway and bunching | No trained model; dashboard scenario is illustrative | Derive headway labels from ordered telemetry; start with a measured rules baseline, then validate a forecasting model against held-out routes and days |
| What-if dispatch effect | Illustrative formula, not a forecast | Collect interventions and outcomes (extra vehicle, insertion stop/time, horizon); train a counterfactual or simulation model and validate it before replacing the demo formula |
| Passenger demand / capacity | Not modeled | Requires passenger count, load/capacity and service frequency data |
| Congestion effects | Not modeled | Requires road traffic observations aligned by segment and event time |

The dashboard's synthetic network snapshot remains a demo provider. NDTP device IDs are not mapped to MoscowMap route IDs, and the supplied emulator does not follow route shapes. A route-level live dashboard therefore still needs a stable vehicle-to-route/variant registry or a source feed that provides those identifiers.

## Handoff boundary

For a new delay model: train an experiment, compare only runs with matching dataset fingerprint and evaluation protocol, choose a run, copy its complete directory under `runs/`, set `runs/selection.json`, then recreate the ML service. No retraining is needed merely to run the current selected artifact. The active model only predicts the delay target represented in its training data; it cannot answer demand, bunching or intervention-effect questions.

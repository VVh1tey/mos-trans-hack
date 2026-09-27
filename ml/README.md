# ML

Выбрана `experiments.catboost_robust`, run `20260927T210831784612Z-robust-final`.
Модель и метаданные поставляются в `runs/`, активный run задаёт `runs/selection.json`.
`service.py` загружает артефакт и обслуживает `/predict` на порту 8001 внутри Docker.
Внешняя точка входа — backend `/api/predict`.

[Модель, метрики, входные признаки, обучение и запуск](../README.md).
`choose.py` выбирает совместимый run. `catboost_robust.py` содержит обучение,
подготовку признаков и инференс; `test_robust.py` проверяет пропуски, артефакт и HTTP.

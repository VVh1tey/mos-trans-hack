# ML

`train.py` запускает модуль из `experiments/`, вычисляет MAE на test и записывает отдельную папку в `runs/`. `experiments.catboost_clean` очищает пересечения по `tr_id` и обучает CatBoost только на `cur_dev_s`. `compare.py` строит индекс запусков, `choose.py` выбирает CatBoost для онлайн-сервиса. Полный порядок действий — в [инструкции](../docs/experiment-workflow.md).

`service.py` обслуживает `POST /predict` и загружает модель из запуска, указанного в `runs/selection.json`. Признаки для обучения и онлайн-предсказания вычисляются одним модулем эксперимента.

# Команды ML

Запускать из корня репозитория в PowerShell. Данные должны лежать в `dataset/`.

## Обучить и проверить на test

```powershell
docker compose -f compose.train.yaml run --build --rm -e TRAIN_MODULE=experiments.catboost_clean trainer
```

Новый вариант объединяет размеченные train+test, удаляет близкие повторы,
считает временные CV-фолды и отдельные validation/test, затем обучает финальную
модель на всех очищенных метках:

```powershell
docker compose -f compose.train.yaml run --build --rm -e TRAIN_MODULE=experiments.catboost_timeseries trainer
```

Команда сама считает MAE на размеченном test и печатает `run_id`. Модель и метрики сохраняются в `runs/<run_id>/`. Посмотреть все запуски, отсортированные по MAE:

```powershell
docker compose -f compose.train.yaml run --rm trainer python compare.py
```

## Выбрать запуск и сделать сабмит

Подставить нужный `run_id` из вывода обучения или `compare.py`:

```powershell
$runId = '20260925T221307Z-15714893'
docker compose -f compose.train.yaml run --rm trainer python choose.py $runId
docker compose -f compose.train.yaml run --build --rm trainer python -m experiments.catboost_clean submit
```

Готовый файл — `outputs/submission.csv`. Для следующего обучения повторить первые две команды, выбрать новый `run_id` и заново создать сабмит.

Для нового временного эксперимента можно создать файл отдельно, не меняя выбранную
для RT модель и старый сабмит:

```powershell
$runId = '20260926T092158Z-3cb15c1b'
docker compose -f compose.train.yaml run --build --rm -e SUBMISSION_FILE=/outputs/submission_timeseries.csv trainer python -m experiments.catboost_timeseries submit $runId
```

Результат: `outputs/submission_timeseries.csv`. Для RT сначала выполните
`docker compose -f compose.train.yaml run --rm trainer python choose.py $runId`,
затем выполните `docker compose up -d --build --force-recreate ml`.

Проверить сохранённый первый CatBoost на временных окнах второго эксперимента
(вывод показывает пересечение с его обучением):

```powershell
docker compose -f compose.train.yaml run --build --rm trainer python -m experiments.catboost_timeseries compare-first 20260925T221307Z-15714893
```

## Проверить RT API

```powershell
docker compose up -d --build ml backend
$body = @{sample_id='check'; cur_dev_s=120} | ConvertTo-Json
Invoke-RestMethod -Uri 'http://127.0.0.1:18000/api/predict' -Method Post -ContentType 'application/json' -Body $body
```

После смены выбранного `run_id` перезапустить ML-сервис: `docker compose up -d --force-recreate ml`. NDTP-поток принимается и отображается в блоке «Симулятор NDTP» на странице «Сеть»; подключение ML к этому потоку пока не реализовано. [Запуск и проверка](docs/ndtp-simulation.md).

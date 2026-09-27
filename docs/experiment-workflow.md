# Эксперименты и передача состояния

## Новый запуск

Распакуйте одинаковый архив данных в `dataset/`. Запуск обучения не зависит от онлайн-Compose:

```sh
docker compose -f compose.train.yaml run --build --rm trainer
docker compose -f compose.train.yaml run --build --rm -e TRAIN_MODULE=experiments.catboost_clean trainer
docker compose -f compose.train.yaml run --build --rm -e TRAIN_MODULE=experiments.catboost_timeseries trainer
docker compose -f compose.train.yaml run --rm -e TRAIN_MODULE=experiments.mean_residual trainer
docker compose -f compose.train.yaml run --rm trainer python compare.py
```

Каждый запуск создаёт `runs/<run_id>/` с моделью, `metrics.json` и `manifest.json`. В манифесте есть модуль, версия признаков, хеши входных CSV и кода, хеш набора данных и Git commit (если передать `GIT_COMMIT` в окружении). `runs/index.csv` — пересоздаваемая таблица для просмотра и сортировки. Сравнивайте MAE только у запусков с одинаковым `dataset_fingerprint` и одинаковым `evaluation_protocol`.

Чтобы попробовать новую модель или признаки, создайте `ml/experiments/<name>.py` с `FEATURE_SET` и тремя функциями:

```python
def fit(train_rows, dataset_root): ...
def predict(model, rows, dataset_root, split): ...
def save_model(model, run_dir): ...  # возвращает путь к файлу в run_dir
```

Затем запустите `docker compose -f compose.train.yaml run --build --rm -e TRAIN_MODULE=experiments.<name> trainer`. `dataset_root` даёт доступ к остальным CSV, а `split` позволяет найти файлы train/test. Код признаков должен быть одинаковым при проверке и онлайн-инференсе. Онлайн-адаптер поддерживает два эксперимента CatBoost; для другого модуля потребуется добавить загрузку модели и предсказание в `ml/service.py`.

Выберите совместимый запуск по ID из `runs/index.csv`:

```sh
docker compose -f compose.train.yaml run --rm trainer python choose.py <run_id>
docker compose up -d --force-recreate ml
```

`experiments.catboost_clean` использует только `cur_dev_s`. Перед обучением модуль
исключает из train все `tr_id`, которые встречаются в test или validate; исходные CSV
не меняются. Модель сохраняется как `catboost.cbm`, а после выбора запуска онлайн-сервис
загружает этот файл. Для проверки RT-предсказания поднимите `docker compose up -d --build ml backend`
и отправьте JSON с `sample_id` и `cur_dev_s` на `POST http://localhost:18000/api/predict`.

Для отправки на платформу после выбора запуска выполните:

```sh
docker compose -f compose.train.yaml run --build --rm trainer python -m experiments.catboost_clean submit
```

Команда создаёт `outputs/submission.csv` в формате `sample_id;prediction`, проверяя
совпадение ID с шаблоном организаторов.

`experiments.catboost_timeseries` использует разметку из train и test. Он удаляет
повторную точку той же машины за 5 минут, если совпали `cur_dev_s` и ответ;
для оценки делит данные по времени на ранний train, отдельные validation и test,
делает три последовательных CV-фолда и оставляет 15 минут зазора между окнами.
Финальная модель затем обучается на всех очищенных размеченных точках. Скрытый
validate не имеет ответов и служит только для сабмита. Его MAE узнать локально нельзя.
Чтобы создать отдельный файл без смены активной модели, используйте:

```sh
docker compose -f compose.train.yaml run --build --rm -e SUBMISSION_FILE=/outputs/submission_timeseries.csv trainer python -m experiments.catboost_timeseries submit <run_id>
```

MAE этого эксперимента рассчитан на других временных окнах, поэтому его нельзя
напрямую сравнивать с MAE первого CatBoost на исходном test.

`runs/selection.json` фиксирует активный выбор. Откат — повторить `choose.py` со старым ID.

## Работа командой

Код и изменения контрактов передавайте через PR. Для результатов используйте одну общую папку `runs/` на общей машине или синхронизируемом диске: копируйте целые папки `runs/<run_id>/`, не переименовывая и не изменяя их. После копирования запустите `compare.py`. Одновременно записывать один и тот же run нельзя; уникальный ID запуска исключает коллизии. Файлы датасета передавайте отдельно через разрешённый для задачи канал; убедитесь, что у команды одинаковый `dataset_fingerprint`. Не коммитьте данные, модели и дампы в Git.

## Передача организаторам или на другую машину

Из корня репозитория в PowerShell выполните `./infra/export-handoff.ps1`. Скрипт требует чистый Git, создаёт архив в `handoff/` с исходниками текущего коммита, полным `runs/`, дампом БД `transport` и контрольными SHA256. С `-IncludeDataset` добавляются `dataset/` и `data/`; проверьте правила передачи данных организаторам. PostgreSQL должен работать. Архив передавайте выбранным командой каналом, вне Git.

На другой машине распакуйте архив, перейдите в `source/` и выполните `./infra/restore-handoff.ps1 -BundleRoot <путь-к-распакованному-архиву> -Force`. Скрипт проверяет хеш дампа, переносит папку запусков и восстанавливает базу `transport`. `-Force` нужен потому, что восстановление заменяет содержимое существующей локальной БД. Требуются Docker Compose и PowerShell. Пароли и локальный `.env` в архив не входят; если пароль PostgreSQL менялся, задайте его в целевой `.env` до восстановления.

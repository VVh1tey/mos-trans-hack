# Прогноз задержек городского транспорта

Запускаемый каркас для хакатона. Задача: по данным, доступным в момент `T`, предсказать задержку в секундах на остановке с плановым прибытием в `(T + 10 минут, T + 15 минут]`. Основная метрика — MAE; формат отправки — `sample_id;prediction`.

## Структура

| Путь | Назначение |
| --- | --- |
| `ml/` | Обучение, эксперименты, выбор модели и HTTP-инференс |
| `backend/` | API и заглушки ingest, worker, scheduler |
| `frontend/` | Демонстрационная панель; рабочий интерфейс ещё предстоит сделать |
| `contracts/` | Форматы обмена между компонентами |
| `infra/` | PostgreSQL, Redis, Prometheus, Grafana, nginx |
| `docs/` | Схемы и архитектурные решения |
| `dataset/`, `runs/`, `data/` | Локальные данные и результаты; исключены из Git |

## Онлайн-контур

Нужны Docker и Docker Compose:

```sh
docker compose up --build -d --wait
```

| Сервис | Адрес | Состояние |
| --- | --- | --- |
| Панель | `http://localhost:18080` | Демонстрационный экран |
| Backend | `http://localhost:18000/health` | Проксирует `POST /api/predict` в ML |
| Grafana | `http://localhost:13000` | Состояние сервисов; `admin` / `admin_local` |
| Prometheus | `http://localhost:19090/targets` | Метрики процессов |
| NDTP ingest | `localhost:9201` | Пока считает байты без разбора пакетов |

Пробный запрос: `POST http://localhost:18000/api/predict` с JSON `{"sample_id":"demo","cur_dev_s":42}`. Пока модель не выбрана, ML возвращает `42` и имя `fallback-cur-dev`. PostgreSQL содержит таблицы `predictions` и `alerts`; Redis и все online-процессы поднимаются, но обработку реальной телеметрии ещё нужно реализовать.

Остановить: `docker compose down`. Данные PostgreSQL, Redis и Grafana остаются в Docker volumes. Выданный эмулятор включается отдельно: `docker load -i dataset/ndtp-telemetry-emulator.tar`, затем `docker compose --profile emulator up -d emulator`. Его API — `http://localhost:18081`; укажите `targetHost: ingest`, `targetPort: 9201`.

## Обучение и выбор модели

Распакуйте архив организаторов в `dataset/` так, чтобы появились `labels/labels_train.csv` и `labels/labels_test.csv`. Онлайн-контур для обучения не нужен:

```sh
docker compose -f compose.train.yaml run --build --rm trainer
docker compose -f compose.train.yaml run --rm -e TRAIN_MODULE=experiments.mean_residual trainer
docker compose -f compose.train.yaml run --rm trainer python compare.py
docker compose -f compose.train.yaml run --rm trainer python select.py <run_id>
docker compose up -d --force-recreate ml
```

Каждый запуск создаёт отдельную папку `runs/<run_id>/` с `manifest.json`, `metrics.json` и файлом модели. `compare.py` создаёт `runs/index.csv`. `select.py` копирует совместимую модель в `runs/selected.json`, откуда её читает онлайн-сервис. Сравнивайте MAE только для одинакового `dataset_fingerprint`. Добавление признаков и моделей, общий обмен результатами и передача проекта описаны в [инструкции по экспериментам](docs/experiment-workflow.md).

## Разработка

Код присылайте через Git и PR; датасет, веса и `runs/` в Git не добавляйте. В PR укажите команду запуска, входы, выходы и способ проверки. Сверяйте API с [контрактами](contracts/README.md), а поток и границы заглушек — с [архитектурными решениями](docs/architecture-decisions.md). Один проверяемый кусок работы на PR удобнее для интеграции.

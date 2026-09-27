# Прогноз задержек городского транспорта

**Сдача хакатона:** [инструкция для жюри, состав пакета и ограничения](docs/JURY.md) · [результаты сабмитов](RESULTS.md).

Запускаемый каркас для хакатона. Задача: по данным, доступным в момент `T`, предсказать задержку в секундах на остановке с плановым прибытием в `(T + 10 минут, T + 15 минут]`. Основная метрика — MAE; формат отправки — `sample_id;prediction`.

## Структура

| Путь | Назначение |
| --- | --- |
| `ml/` | Обучение, эксперименты, выбор модели и HTTP-инференс |
| `backend/` | API и заглушки ingest, worker, scheduler |
| `frontend/` | React-дашборд: карта сети, маршруты, инциденты и What-if на HTTP-моках |
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
| Панель | `http://localhost:18080` | Рабочий интерфейс с демонстрационным API |
| Backend | `http://localhost:18000/health` | Проксирует `POST /api/predict` в ML |
| Grafana | `http://localhost:13000` | Состояние сервисов; `admin` / `admin_local` |
| Prometheus | `http://localhost:19090/targets` | Метрики процессов |
| NDTP ingest | `localhost:9201` | Принимает NDTP, проверяет CRC и декодирует Nav00 |

Фронтенд можно запустить без Docker: `python backend/app.py`, затем в другом
терминале `cd frontend`, `npm ci`, `npm run dev` → `http://127.0.0.1:5173`.
[Экраны, данные и проверки](frontend/README.md) · [контракт Dashboard API](contracts/dashboard.md).

Пробный запрос: `POST http://localhost:18000/api/predict` с JSON `{"sample_id":"demo","cur_dev_s":42}`. Пока модель не выбрана, ML возвращает `42` и имя `fallback-cur-dev`. PostgreSQL содержит таблицы `predictions` и `alerts`; Redis и все online-процессы поднимаются, но обработку реальной телеметрии ещё нужно реализовать.

Остановить: `docker compose down`. Данные PostgreSQL, Redis и Grafana остаются в Docker volumes. Выданный эмулятор включается отдельно: `docker load -i dataset/ndtp-telemetry-emulator.tar`, затем `docker compose --profile emulator up -d --build`. На странице «Сеть» (`http://localhost:18080`) блок «Симулятор NDTP» запускает и останавливает поток, показывает позиции, скорость и свежесть пакетов. [Инструкция и границы интеграции](docs/ndtp-simulation.md). API самого эмулятора — `http://localhost:18081`.

## Обучение и выбор модели

Распакуйте архив организаторов в `dataset/` так, чтобы появились `labels/labels_train.csv` и `labels/labels_test.csv`. Онлайн-контур для обучения не нужен:

```sh
docker compose -f compose.train.yaml run --build --rm trainer
docker compose -f compose.train.yaml run --rm -e TRAIN_MODULE=experiments.mean_residual trainer
docker compose -f compose.train.yaml run --rm trainer python compare.py
docker compose -f compose.train.yaml run --rm trainer python choose.py <run_id>
docker compose up -d --force-recreate ml
```

Каждый запуск создаёт отдельную папку `runs/<run_id>/` с `manifest.json`, `metrics.json` и файлом модели. `compare.py` создаёт `runs/index.csv`. `choose.py` записывает активный запуск в `runs/selection.json`; онлайн-сервис загружает модель из папки запуска. Сравнивайте MAE только для одинакового `dataset_fingerprint`. Добавление признаков и моделей, общий обмен результатами и передача проекта описаны в [инструкции по экспериментам](docs/experiment-workflow.md).

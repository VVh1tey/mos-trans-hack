# Инфраструктура

Корневой `compose.yaml` поднимает онлайн-контур: PostgreSQL приложения, Redis, API, ML-сервис, заглушки обработки телеметрии, Prometheus, Grafana и демонстрационную панель. `compose.train.yaml` запускает отдельную одноразовую задачу обучения без сетевых зависимостей.

Схема PostgreSQL создаётся `postgres/init.sh`, метрики и дашборд — в `prometheus/` и `grafana/`. Пароли для локального запуска можно переопределить через `POSTGRES_PASSWORD` и `GRAFANA_PASSWORD` в `.env`. Папки `dataset/` и `runs/` находятся на хосте; Docker volumes хранят состояние онлайн-сервисов. Перенос проекта описан в [инструкции](../docs/experiment-workflow.md).

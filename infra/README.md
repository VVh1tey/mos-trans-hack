# Инфраструктура

[Запуск и обязательные файлы](../README.md).
`compose.yaml` поднимает backend, ML, ingest, frontend, Prometheus и Grafana.
`compose.train.yaml` запускает отдельную задачу обучения.

`nginx.conf` раздаёт frontend и проксирует API. Настройки мониторинга находятся
в `prometheus/` и `grafana/`. Данные мониторинга сохраняются в Docker volumes,
датасет и модель монтируются с хоста.

`export-handoff.ps1 -IncludeDataset` создаёт архив из последнего коммита,
локальных runs и данных; перед экспортом нужно закоммитить подготовленный index.
При ручном переносе распакуйте исходники, положите датасет и выбранный run
по путям из README и выполните `docker compose up -d --build --wait`.

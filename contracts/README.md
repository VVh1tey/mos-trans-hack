# HTTP-контракты

Актуальные схемы: [backend/openapi.json](../backend/openapi.json).
После запуска доступен [Swagger UI](http://localhost:18000/docs).

- `POST /api/predict`: JSON с `sample_id` и признаками; ответ — `prediction`
  (задержка в секундах) и `model` (run ID).
- `GET /api/dashboard/simulation`: состояние исторического воспроизведения,
  телеметрия и прогнозы.
- `POST /api/dashboard/simulation`: `action` = `start`, `stop`, `reset` или `speed`;
  скорость задаётся полем `speed` (1, 10, 60, 300, 3600).
- `GET /api/dashboard`: каталог и демонстрационные маршрутные показатели.

[Описание данных и ограничений](../README.md) ·
[Пользовательский гайд](../docs/dashboard-guide.md).

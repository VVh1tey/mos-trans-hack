# NDTP: запуск и остановка из интерфейса

Используется предоставленный `ndtp-telemetry-emulator:1.0`, без изменения его образа.

```powershell
docker load -i dataset/ndtp-telemetry-emulator.tar
docker compose --profile emulator up -d --build
```

Открыть http://localhost:18080, раздел **Сеть**, блок **Симулятор NDTP**.
Нажать **Запустить симуляцию**: пять устройств отправляют навигацию раз в две секунды.
Карта и таблица получают данные приёмника через backend, обновление каждые две секунды.
Кнопка **Остановить** отправляет эмулятору конфигурацию с `units: []`; контейнер остаётся доступным для следующего запуска.
Последние позиции сохраняются, через 10 секунд без пакетов становятся устаревшими.
После обновления страницы статус читается из настоящей конфигурации эмулятора.

Если основной стек уже собран, включить сервис: `docker compose --profile emulator up -d emulator`.
При изменении исходников приёмника/API/фронта пересобрать соответствующие сервисы.
При первом запуске контейнера эмулятор выключен. Его конфигурация сбрасывается при перезапуске контейнера.

## Как проходит пакет

`emulator → ingest:9201 (TCP NDTP) → ingest:9101/telemetry → backend → /api/dashboard/simulation → браузер`.

Приёмник собирает кадры из произвольных TCP-фрагментов, проверяет CRC-16/Modbus с перестановкой байтов,
принимает handshake, извлекает первую ячейку Nav00: ID терминала, время, координаты с учётом знака,
валидность GPS, скорость, курс, высоту и спутники. Остальные сенсорные ячейки не интерпретируются.
Ответ на handshake не нужен предоставленному эмулятору по его спецификации.

Состояние последних позиций хранится в памяти ingest (не более 10 000 устройств), после его перезапуска очищается.
Счётчики пакетов/байтов/ошибок и число соединений доступны Prometheus на `/metrics` приёмника.
Повреждённые кадры не попадают в снимок; недостоверные GPS-позиции остаются в таблице, но не рисуются на карте.
Статус отправки и факт поступления пакетов показаны отдельно. При недоступности API интерфейс сообщает об ошибке.

## API управления

- `GET /api/dashboard/simulation`: состояние конфигурации эмулятора, доступность приёмника, счётчики и последние позиции.
- `POST /api/dashboard/simulation`, JSON `{"action":"start"}`: запускает стандартный набор устройств, если список units пуст.
- `POST /api/dashboard/simulation`, JSON `{"action":"stop"}`: очищает список units, сохраняя адрес приёмника.

Повторный start уже работающего эмулятора не сбрасывает генератор и не заменяет загруженную вручную конфигурацию.
Для собственной конфигурации остаётся API эмулятора http://localhost:18081/api/config.
В Docker targetHost должен быть `ingest`, targetPort — `9201`.

Backend настраивается через `EMULATOR_URL`, `INGEST_URL`, `NDTP_TARGET_HOST`, `NDTP_TARGET_PORT`.
Compose задаёт внутренние адреса. При локальном запуске backend с Docker-приёмником нужно обеспечить доступ к его HTTP-порту
и указать соответствующий `INGEST_URL` (по умолчанию локального backend — `http://127.0.0.1:9101`).

## Границы интеграции

Данные в блоке NDTP — живой поток предоставленного симулятора. Устройства автоматически движутся около Москвы;
они не воспроизводят CSV и не следуют геометрии маршрутов. `unitId` пока не сопоставлен с `tr_id` и маршрутами.
Поэтому прогнозы, маршруты и инциденты ниже остаются отдельно обозначенной демонстрацией.
ML-инференс, Redis Stream и архивирование этого потока не подключены.

## GPS fixes, ordering and replay clock

`ingest.py` keeps event time (`eventTime`) separate from receiver time (`receivedAt`). The event time orders fixes and drives replay staleness; receiver time measures transport freshness only. An older event is ignored. Repeating the same packet ID at the same event time is a duplicate and is ignored. A newer packet with an invalid GPS flag updates packet freshness and quality, but retains the last valid coordinate.

Duplicate packets, late packets, invalid fixes and suspect fixes have separate counters in the telemetry snapshot and Prometheus metrics.

Nav00 quality is `poor` when a reported satellite count is 1–3 or a reported PDOP exceeds 20; zero means the emulator/feed did not supply that quality field. The receiver rejects a fix as `suspect` if its implied speed from the previous accepted position exceeds `GPS_MAX_SPEED_KMH` (default 160 km/h), or if event time does not advance. It retains the old coordinate and does not use the suspect coordinate as the next distance baseline. A future production feed should add device accuracy thresholds and route-aware map matching.

The map should keep a valid last-known position for up to 120 seconds (`GPS_RETAIN_SECONDS`), fade it and mark it as GPS-lost/suspect while the fix is invalid or older than the 90-second replay freshness window, then remove it. Replay ages are computed against virtual `currentTime`, never wall-clock receipt time, so changing replay speed does not change staleness. Real-time receiver age remains available separately for diagnostics. Current snapshots retain the last position and expose its age/status; clients should interpolate only between accepted fixes, never toward a rejected coordinate.

Recommended follow-up for production transport is a short event-time ordered buffer (approximately 2 seconds) before publishing so moderately late packets can be inserted in order. Reject duplicates by `(unitId, packetId, eventTime)`, reject packets beyond the allowed lateness window, and persist raw received packets separately from the cleaned latest-position state. Map-match valid fixes to the vehicle's assigned route before accepting a large cross-street deviation; do not bridge a long GPS outage with a straight line.

## MoscowMap routes

Run `python scripts/scrape_moscowmap.py` from the repository root. It writes `data/moscowmap/routes.json`, `routes.csv`, `stops.csv`, `routes.geojson`, URL checkpoints and crawl errors. The backend reads that directory and merges the route catalog into the dashboard. The scraper is resumable and accepts `--limit` for a small crawl. Some MoscowMap pages may return HTTP 403 to automated clients; the command records failures rather than claiming an empty crawl is complete. The site should be fetched from an environment where its terms and access rules permit it.

The route shape is extracted from embedded coordinates. Stop coordinates are used when they are present close to stop records in the page source; otherwise the importer places stops along the published shape by sequence. Such fallback coordinates are approximate and must be replaced with source stop coordinates before using them for navigation or operational dispatch.

## Проверка

```powershell
python -m unittest discover -s backend -p 'test_*.py'
cd frontend
$env:PLAYWRIGHT_BASE_URL='http://127.0.0.1:18080'
$env:NDTP_LIVE_TEST='1'
npx playwright test tests/simulation.spec.ts
```

Живой тест запускает и останавливает реальный эмулятор, проверяет изменение координат, рост счётчика,
отсутствие ошибок NDTP, прекращение пакетов, старение данных, повторный запуск и восстановление статуса после reload.
Тест завершает работу с выключенной симуляцией. Проверка недоступности эмулятора использует подмену HTTP-ответа.

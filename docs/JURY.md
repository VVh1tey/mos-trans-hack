# Инструкция для жюри

## Что передать вместе со ссылкой на исходники

Репозиторий содержит код трёх модулей и Docker Compose. Для воспроизводимого запуска дополнительно передайте архивы `dataset/` (выданный организаторами набор и образ эмулятора) и `runs/` (выбранная CatBoost-модель). Эти каталоги исключены из Git. В `runs/selection.json` должен быть указан существующий запуск с `manifest.json` и `catboost.cbm`. Файл для раздела Data Science — `outputs/submission_timeseries.csv` (151 строка, `sample_id;prediction`); он также исключён из Git. Его платформенный score — 0,45045 (см. [результаты](../RESULTS.md)). Публичную ссылку на эти файлы нужно добавить в форму платформы отдельно.

## Запуск и проверка за несколько минут

Нужны Docker Desktop/Engine с Compose и распакованные данные в перечисленных каталогах. Из корня проекта:

```powershell
docker load -i dataset/ndtp-telemetry-emulator.tar
docker compose --profile emulator up --build -d --wait
docker compose ps
```

Откройте [панель](http://localhost:18080), [health API](http://localhost:18000/health), [Grafana](http://localhost:13000) (`admin` / `admin_local`) и [цели Prometheus](http://localhost:19090/targets). Порты привязаны к `127.0.0.1`; для удалённого просмотра необходим отдельный защищённый доступ к машине с Docker.

На странице «Сеть» в блоке «Исторические данные · test» нажмите «Запустить»; скорость можно увеличить до ×3600. Карта показывает принятые NDTP-пакеты и свежесть координат. Воспроизведение подаёт поток через NDTP-приёмник и вызывает выбранный ML-сервис для ТС с плановой остановкой через 10–15 минут. Прогноз обновляется по новым пакетам не чаще одного раза в 120 секунд виртуального времени для одной остановки. В test первое подходящее окно возникает в 02:03:03 МСК; до него ноль прогнозов ожидаем. Отдельные размеченные точки служат для честной оценки MAE: фактическое прибытие открывается только после его наступления. API: `GET /api/dashboard/simulation`, `GET /api/predictions`. Прямой пробный вызов модели через backend:

```powershell
Invoke-RestMethod http://localhost:18000/api/predict -Method Post -ContentType 'application/json' -Body '{"sample_id":"jury-demo","cur_dev_s":42}'
```

Показанные маршруты, инциденты и What-if на основном дашборде — демонстрационные данные. ID устройств внешнего эмулятора не связаны с `tr_id` и маршрутами датасета; его пакеты сами по себе не создают ML-прогнозы. Сквозной сценарий ML демонстрируется **историческим воспроизведением**, которое использует тот же NDTP-декодер. Отдельный внешний эмулятор можно запускать через его API на `http://localhost:18081/api/config` по [инструкции NDTP](ndtp-simulation.md). Вероятность задержки, причина сбоя и эффект What-if не обучены и не должны трактоваться как результаты модели. Подробнее: [статус модели](online-model-status.md).

## Метрики, документация и завершение

Метрики доступны по `/metrics` у backend, ML и ingest через Prometheus/Grafana. График задержки HTTP/ML запросов показывает измеренные значения; подтверждённого нагрузочного теста и гарантии менее 2 секунд на большой поток нет. Документация: [PyDoc HTML](pydoc/index.html), [OpenAPI JSON](../backend/openapi.json), [Swagger UI](http://localhost:18000/docs) и [контракт Dashboard API](../contracts/dashboard.md). Swagger UI загружает JavaScript и CSS из CDN, поэтому для страницы нужен интернет; сам `/openapi.json` доступен локально. PyDoc пересоздаётся командой `docker compose run --rm --no-deps -v "${PWD}:/repo" -w /repo ml python scripts/build_pydoc.py` в PowerShell. Остановить контур: `docker compose --profile emulator down`.

## Поля формы платформы

1. **Data Science:** загрузить `outputs/submission_timeseries.csv`.
2. **Система:** ссылка на доступный жюри репозиторий и отдельный пакет `dataset/` + `runs/` (или образ работающей машины).
3. **Инструкция:** прямая ссылка на этот файл.
4. **Документация:** ссылки на `docs/pydoc/index.html`, `backend/openapi.json`, работающий `/docs` и `contracts/dashboard.md`.
5. **Производительность и дополнительные возможности:** ссылка на этот файл, `docs/online-model-status.md` и `docs/optional-features.md`; не заявлять непроверенную пропускную способность.

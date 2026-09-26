# Демо-диспетчерская

React + TypeScript + Vite + MapLibre. Обзор сети, маршруты, инциденты,
история с CSV-экспортом, What-if, настройки и карточки транспорта.

## Запуск

Нужны Python 3.12+ и Node 22.12+. Из корня проекта в первом терминале:

```sh
python backend/app.py
```

Во втором терминале:

```sh
cd frontend
npm ci
npm run dev
```

Открыть http://127.0.0.1:5173. Docker и ML для демо не нужны.
Для другого адреса API задайте `API_PROXY_TARGET` перед запуском Vite.
Backend поддерживает `HOST` и `PORT` (по умолчанию 0.0.0.0:8000).

## Данные

Демо-API: `backend/dashboard.py`. Маршруты: `backend/demo/routes.json`.
Исходные датасеты для запуска не нужны. Транспорт и прогнозы синтетические;
What-if использует демонстрационную формулу.
Подложка OpenStreetMap требует интернет, карта — WebGL2.
Избранное и отметки просмотра сохраняются в localStorage.

## Проверки

В каталоге frontend:

```sh
npm run build
npx playwright install chromium
npm run test:e2e
```

Из корня проекта:

```sh
python -m unittest discover -s backend -p test_dashboard.py -v
```

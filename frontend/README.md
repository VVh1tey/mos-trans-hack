# Дашборд

[Запуск всего проекта](../README.md) · [Гайд со скриншотами](../docs/dashboard-guide.md).

React, TypeScript, Vite и MapLibre. Для разработки нужен Node 22.12+.
Сначала запустите backend, ML и ingest через Docker из корня проекта.
Затем в PowerShell:

```powershell
cd frontend
npm ci
$env:API_PROXY_TARGET='http://127.0.0.1:18000'
npm run dev
```

Dev-сервер: http://127.0.0.1:5173. Сборка: `npm run build`.
Для тестов установите Chromium: `npx playwright install chromium`.

```powershell
$env:PLAYWRIGHT_BASE_URL='http://127.0.0.1:5173'
npx playwright test tests/telemetryMotion.spec.ts tests/telemetryMap.spec.ts
```

Тест карты подменяет телеметрию и тайлы для воспроизводимой проверки.
Скриншоты руководства снимаются отдельно с работающего Docker-дашборда:
`node capture-guide.cjs`. Нужен уже запущенный replay с видимыми машинами;
на время съёмки он ставится на паузу и затем возвращается в исходное состояние.

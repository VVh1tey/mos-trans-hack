# MoscowMap route archive

Generated route files belong in this directory. From the repository root run:

```sh
python scripts/scrape_moscowmap.py
```

The crawler writes `routes.json`, `routes.csv`, `stops.csv`, and `routes.geojson` here. The backend imports `routes.json` automatically. No catalog is committed yet because MoscowMap returned HTTP 403 to the crawler during this session; rerun from a network where the site permits access. A crawl that downloads zero route pages does not write an empty catalog.

MoscowMap renders its route links in JavaScript. If a normal HTTP response has no links, the crawler uses the Playwright package from `frontend/` to open a browser, try the number-range tabs and expand “Посмотреть все”, then visit route pages. Install the frontend dependencies and Chromium once before scraping:

```sh
cd frontend
npm ci
npx playwright install chromium
cd ..
python scripts/scrape_moscowmap.py --limit 1
```

The browser is visible by default. Set `MOSCOWMAP_HEADLESS=1` to run it without a window when the host has no desktop session.

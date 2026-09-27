# MoscowMap route archive

Generated route files belong in this directory. From the repository root run:

```sh
python scripts/scrape_moscowmap.py
```

The crawler writes `routes.json`, `routes.csv`, `stops.csv`, and
`routes.geojson` here. The backend imports `routes.json` automatically.
MoscowMap has returned empty/non-page responses to command-line fetches in this
environment; the site may require browser JavaScript and may restrict some
networks. A crawl that downloads zero route pages does not write an empty
catalog. Official Moscow open-data snapshots are also committed under
`data/additional/` and provide a reproducible baseline without a live crawl.

If a normal HTTP response has no links, the crawler uses Playwright from
`frontend/` to render pages, try the number-range tabs, expand the full route
list, and visit route pages. Install dependencies and Chromium once before
scraping:

```sh
cd frontend
npm ci
npx playwright install chromium
cd ..
python scripts/scrape_moscowmap.py --limit 1
```

The Playwright worker runs headless by default. Set `MOSCOWMAP_HEADLESS=0` to
show a browser window while diagnosing the site.

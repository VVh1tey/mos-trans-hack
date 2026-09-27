# MoscowMap route archive

Generated route files belong in this directory. From the repository root run:

```sh
python scripts/scrape_moscowmap.py
```

The crawler writes `routes.json`, `routes.csv`, `stops.csv`, and `routes.geojson` here. The backend imports `routes.json` automatically. No catalog is committed yet because MoscowMap returned HTTP 403 to the crawler during this session; rerun from a network where the site permits access. A crawl that downloads zero route pages does not write an empty catalog.

# Route imports and source data

The backend loads JSON files from this directory automatically. The MoscowMap
browser crawler writes `routes.json`, `routes.csv`, `stops.csv`, and
`routes.geojson` here. A crawl that downloads zero route pages does not write an
empty catalog.

## Daytime OpenStreetMap routes

Run from a network that can reach one of the public Overpass servers:

```sh
python scripts/scrape_osm_day_routes.py
```

The script writes `osm_day_routes.json` here, where Docker and the local
backend import it automatically. It includes route geometry, the ordered stop
members found on each OSM route relation, query metadata and license
attribution. `--limit N` is for a small trial export; omit it for the full
query. Public route mapping can be incomplete, so this archive represents the
OSM-mapped daytime routes in the query area, not a guaranteed complete
official route catalog. Review its route count and missing relation summary
before treating it as complete.

The source data is OpenStreetMap under ODbL 1.0. Keep the attribution visible
where the data is displayed and retain the source metadata in the archive.
See <https://www.openstreetmap.org/copyright>.

## MoscowMap fallback

MoscowMap has returned HTTP 403 in some networks. Its crawler can use Playwright
to render JavaScript pages if the site is reachable:

```sh
cd frontend
npm ci
npx playwright install chromium
cd ..
python scripts/scrape_moscowmap.py --limit 1
```

Run `python scripts/scrape_moscowmap.py` without `--limit` for a complete
crawl. Treat its content according to MoscowMap's reuse terms; no open-data
license has been established for that site.

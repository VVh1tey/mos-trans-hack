# Route imports and source data

The backend loads JSON files from this directory automatically. The MoscowMap
browser crawler writes `routes.json`, `routes.csv`, `stops.csv`, and
`routes.geojson` here. A crawl that downloads zero route pages does not write an
empty catalog.

## Preferred source: Moscow open-data schedules

The local snapshots under `data/additional/` contain the route catalog (60664)
and stop catalog with coordinates (60662), but they do not include daytime stop
sequences or route shapes. The official portal also publishes related datasets:

- 60661, trip schedules: route/trip key, stop code, stop order and scheduled time;
- 60666, route calendar: service days and effective dates;
- 60665, number of vehicle departures/exits.

The sequence can be joined to stop coordinates by stop code and to the route
catalog by route code. These official records are the right source for the
daytime stop order. They do not by themselves provide a road-following shape;
that still needs a separate geometry source or route reconstruction. Dataset
60661 is very large and the portal has had download/API reliability issues, so
no full local schedule export is committed yet.

## OpenStreetMap geometry fallback

Run from a network that can reach one of the public Overpass servers:

```sh
python scripts/scrape_osm_day_routes.py
```

The script writes `osm_day_routes.json` here, where Docker and the local
backend import it automatically. It includes route geometry, ordered stop
members present in each OSM route relation, query metadata and license
attribution. `--limit N` is for a small trial export; omit it for the full
query. This is useful for geometry and cross-checking, but public route mapping
can be incomplete. Review its route count against official datasets 60661 and
60664 before using it as the full daytime catalog.

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

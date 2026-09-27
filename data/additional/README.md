# Moscow open transport data snapshots

These source snapshots were downloaded from the Moscow Government open-data
portal (`https://data.mos.ru/`) on the dates included in their filenames. They
are committed so route preparation and demo startup do not depend on network
access or a MoscowMap crawl.

| File | Portal dataset | Contents | Snapshot date |
| --- | --- | --- | --- |
| `data-60662-22-09-2026.csv` | 60662, stops | Stop identifiers, names, types and point geometry | 2026-09-22 |
| `data-60664-22-09-2026.csv` | 60664, routes | Route identifiers, numbers, names and transport type | 2026-09-22 |
| `data-62904-11-08-2026.json` | 62904, night routes | Night-route metadata and route geometry | 2026-08-11 |

The CSV exports are UTF-8, semicolon-delimited, and include a second descriptive
header row. The stop catalog has about 17,800 records; the route catalog has
about 939. Dataset 62904 contains 18 night routes with geometry. These snapshots
do not provide ordered stops or full geometry for every daytime route. Do not
infer an authoritative stop sequence from the nearest-stop demo fixture.

The reproducible dashboard fixture is built with:

```sh
python scripts/prepare_dashboard_data.py
```

That script currently uses dataset 62904 for route lines and finds approximate
nearby stops from dataset 60662. Dataset 60664 is preserved as the route
catalog source for future route import work, but is not yet joined to complete
route shapes or ordered stop sequences.

For current reuse terms and attribution requirements, consult the dataset
cards and the portal's terms on [data.mos.ru](https://data.mos.ru/). Preserve
the dataset IDs and retrieval dates when publishing derived data.

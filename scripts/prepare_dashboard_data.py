"""Build a small, reproducible map fixture from the supplied Moscow open data.

Stop samples are nearest real stops, NOT an authoritative ordered route schedule.
No relation to training tr_id values is asserted.
"""
import csv
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data/additional'


def main():
    raw = json.loads((SOURCE / 'data-62904-11-08-2026.json').read_text(encoding='utf-8-sig'))
    stops = []
    with (SOURCE / 'data-60662-22-09-2026.csv').open(encoding='utf-8-sig') as file:
        for row in csv.DictReader(file, delimiter=';'):
            match = re.search(r'coordinates=\[([\d.]+),\s*([\d.]+)\]', row['Centroid'])
            if match:
                stops.append({'id': row['Stop code'], 'name': row['Stop name'], 'coordinates': [float(x) for x in match.groups()]})
    routes = []
    for row in raw:
        coords = row['geoData'][0]['coordinates']
        directions = []
        for line in coords:
            # Sample by distance, not vertex count (road curvature changes vertex density).
            lengths = [0.0]
            for a, b in zip(line, line[1:]):
                lengths.append(lengths[-1] + math.hypot((b[0]-a[0]) * .56, b[1]-a[1]))
            chosen = []
            for i in range(10):
                target = lengths[-1] * i / 9
                p = line[min(range(len(line)), key=lambda j: abs(lengths[j]-target))]
                nearest = min(stops, key=lambda s: ((s['coordinates'][0]-p[0])*.56)**2 + (s['coordinates'][1]-p[1])**2)
                if not chosen or nearest['id'] not in [s['id'] for s in chosen]:
                    chosen.append(nearest)
            directions.append({'coordinates': line, 'stops': chosen})
        # This source file is the published Moscow night-route network; some rows omit hours.
        service_type = 'night'
        routes.append({'id': str(row['global_id']), 'number': row['RouteNumber'], 'name': row['RouteName'].replace(' - ', ' — '), 'transport': row['TypeOfTransport'], 'serviceType': service_type, 'serviceHours': row['WorkTime'], 'officialInterval': row['StopInterval'], 'directions': directions})
    target = ROOT / 'backend/demo/routes.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({'source': 'data-62904-11-08-2026.json; data-60662-22-09-2026.csv', 'stopMethod': 'nearest sampled stops, approximate order', 'routes': routes}, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'Wrote {len(routes)} routes to {target}')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Download daytime public-transport route relations from OpenStreetMap."""
import argparse
import json
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / 'data/moscowmap/osm_day_routes.json'
BBOX = (55.14, 36.80, 56.02, 37.98)  # south, west, north, east; Moscow metro area
ENDPOINTS = (
    'https://overpass.openstreetmap.ru/api/interpreter',
    'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
    'https://overpass-api.de/api/interpreter',
)
ROUTE_TYPES = {'bus', 'trolleybus', 'tram', 'share_taxi', 'minibus'}
STOP_ROLES = {'stop', 'platform', 'stop_position', 'platform_entry_only',
              'platform_exit_only', 'stop_entry_only', 'stop_exit_only'}
NIGHT_REF = re.compile(r'^\s*(?:н|n)\s*\d', re.IGNORECASE)


def query_text(bbox=BBOX):
    south, west, north, east = bbox
    return f'''[out:json][timeout:180];
rel["type"="route"]["route"~"^(bus|trolleybus|tram|share_taxi|minibus)$"]
  ({south},{west},{north},{east})->.routes;
(.routes;>;);
out body geom;'''


def download(timeout=240):
    payload = urlencode({'data': query_text()}).encode('utf-8')
    last_error = None
    for endpoint in ENDPOINTS:
        request = Request(endpoint, data=payload, headers={
            'User-Agent': 'MoscowDayTransitArchive/1.0 (OpenStreetMap ODbL data import)',
            'Content-Type': 'application/x-www-form-urlencoded; charset=utf-8',
            'Accept': 'application/json',
        })
        for attempt in range(2):
            try:
                with urlopen(request, timeout=timeout) as response:
                    data = json.loads(response.read().decode('utf-8'))
                if data.get('remark') and not data.get('elements'):
                    raise RuntimeError(data['remark'])
                return data, endpoint
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
                last_error = exc
                print(f'Overpass failed ({endpoint}, attempt {attempt + 1}): {exc}')
                if attempt == 0:
                    time.sleep(2)
    raise RuntimeError(f'All Overpass endpoints failed: {last_error}')


def point(item):
    if 'lon' in item and 'lat' in item:
        return [float(item['lon']), float(item['lat'])]
    return None


def distance_sq(a, b):
    return ((a[0] - b[0]) * .56) ** 2 + (a[1] - b[1]) ** 2


def way_geometry(member, elements):
    way = elements.get(('way', member.get('ref')), {})
    coords = [point(p) for p in way.get('geometry', [])]
    coords = [p for p in coords if p]
    role = member.get('role', '').lower()
    if role in {'backward', 'reverse'}:
        coords.reverse()
    return coords


def build_line(members, elements):
    parts, current = [], []
    for member in members:
        if member.get('type') != 'way':
            continue
        coords = way_geometry(member, elements)
        if len(coords) < 2:
            continue
        if not current:
            current = coords
        elif distance_sq(current[-1], coords[0]) < 0.0000001:
            current.extend(coords[1:])
        elif distance_sq(current[-1], coords[-1]) < 0.0000001:
            coords.reverse()
            current.extend(coords[1:])
        else:
            parts.append(current)
            current = coords
    if current:
        parts.append(current)
    return parts


def stop_from(member, elements, route_id, sequence):
    if member.get('role', '').lower() not in STOP_ROLES:
        return None
    element = elements.get((member.get('type'), member.get('ref')), {})
    tags = {**element.get('tags', {}), **member.get('tags', {})}
    coords = point(element)
    if coords is None and element.get('geometry'):
        points = [point(p) for p in element['geometry']]
        points = [p for p in points if p]
        if points:
            coords = [sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points)]
    if coords is None:
        return None
    name = tags.get('name:ru') or tags.get('name') or tags.get('local_name')
    if not name:
        return None
    ref = f'{member.get("type", "node")}-{member.get("ref", sequence)}'
    return {'id': f'{route_id}-{ref}', 'name': name, 'coordinates': coords,
            'sequence': sequence, 'osmElement': ref}


def convert(data, endpoint, limit=0):
    elements = {(item.get('type'), item.get('id')): item for item in data.get('elements', [])}
    relations = [item for item in data.get('elements', [])
                 if item.get('type') == 'relation'
                 and item.get('tags', {}).get('type') == 'route'
                 and item.get('tags', {}).get('route') in ROUTE_TYPES]
    routes, skipped = [], {'night': 0, 'missing_shape_or_stops': 0}
    for relation in sorted(relations, key=lambda item: item['id']):
        tags = relation.get('tags', {})
        number = tags.get('ref') or tags.get('name') or str(relation['id'])
        if NIGHT_REF.match(number):
            skipped['night'] += 1
            continue
        route_id = f'osm-{relation["id"]}'
        members = relation.get('members', [])
        parts = build_line(members, elements)
        parts.sort(key=lambda p: sum((distance_sq(a, b) ** .5) for a, b in zip(p, p[1:])), reverse=True)
        stops = []
        for member in members:
            stop = stop_from(member, elements, route_id, len(stops) + 1)
            if stop and (not stops or distance_sq(stop['coordinates'], stops[-1]['coordinates']) > 0.0000001
                         or stop['name'] != stops[-1]['name']):
                stops.append(stop)
        if not parts or len(parts[0]) < 2 or len(stops) < 2:
            skipped['missing_shape_or_stops'] += 1
            continue
        routes.append({
            'id': route_id, 'number': str(tags.get('ref') or number),
            'name': tags.get('name:ru') or tags.get('name') or str(number),
            'transport': tags.get('route', 'bus'), 'serviceType': 'day',
            'serviceHours': tags.get('opening_hours', ''),
            'officialInterval': tags.get('interval', ''),
            'intervalMinutes': 10, 'source': f'https://www.openstreetmap.org/relation/{relation["id"]}',
            'coordinateQuality': 'OSM route relation; longest connected segment',
            'directions': [{'coordinates': parts[0], 'stops': stops}],
            'segments': parts,
        })
        if limit and len(routes) >= limit:
            break
    archive = {
        'source': 'OpenStreetMap', 'sourceUrl': 'https://www.openstreetmap.org/copyright',
        'queryEndpoint': endpoint, 'queryBbox': list(BBOX), 'license': 'ODbL-1.0',
        'attribution': '© OpenStreetMap contributors',
        'fetchedAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'sourceRelations': len(relations), 'skipped': skipped, 'routes': routes,
    }
    return archive


def write_archive(archive, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    routes = archive['routes']
    # This location is mounted by Docker and loaded by backend/dashboard.py.
    # Keeping geometry, stops and attribution in one JSON file also avoids
    # duplicate CSVs being mistaken for route-import files.
    output.write_text(json.dumps(archive, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    print(f'Wrote {len(routes)} daytime route variants from {archive["sourceRelations"]} relations; '
          f'skipped={archive["skipped"]}; endpoint={archive["queryEndpoint"]}; output={output}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT,
                        help='route JSON; by default the backend import directory is used')
    parser.add_argument('--limit', type=int, default=0, help='maximum output routes; 0 means no limit')
    parser.add_argument('--timeout', type=int, default=240)
    args = parser.parse_args()
    data, endpoint = download(args.timeout)
    archive = convert(data, endpoint, args.limit)
    if not archive['routes']:
        raise SystemExit(f'No route relations with both geometry and at least two located stops; '
                         f'source relations={archive["sourceRelations"]}, skipped={archive["skipped"]}')
    write_archive(archive, args.output)


if __name__ == '__main__':
    main()

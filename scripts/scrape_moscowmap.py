#!/usr/bin/env python3
"""Download MoscowMap route pages and export route/stop/shape CSV and GeoJSON.

The site may deny automated requests. This scraper uses conservative pacing,
retries, and checkpoints its discovered URLs so a crawl can be resumed.
"""
import argparse
import csv
from html import unescape
from html.parser import HTMLParser
import json
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

BASE = 'https://www.moscowmap.ru'
INDEX = BASE + '/marshruty-gorodskogo-transporta.html'
ROUTE_PATH = re.compile(r'^/marshruty-gorodskogo-transporta/[^/]+/moscow/[^?#]+\.html$')
STOP_LINE = re.compile(r'^\s*(\d+)\s*[●•]\s*(.+?)\s*$')
COORD_PAIR = re.compile(r'(?<![\w.])(-?\d{2,3}\.\d{4,})\s*[,; ]\s*(-?\d{2,3}\.\d{4,})(?![\w.])')


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.text, self.h1 = [], [], []
        self.in_h1 = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('href'):
            self.links.append((attrs['href'], []))
        if tag == 'h1':
            self.in_h1 = True
        if tag in {'br', 'p', 'li', 'tr', 'h1', 'h2', 'h3', 'div'}:
            self.text.append('\n')

    def handle_endtag(self, tag):
        if tag == 'h1':
            self.in_h1 = False
        if tag in {'p', 'li', 'tr', 'h1', 'h2', 'h3', 'div'}:
            self.text.append('\n')

    def handle_data(self, data):
        value = ' '.join(data.split())
        if value:
            self.text.append(' ' + value + ' ')
            if self.in_h1:
                self.h1.append(value)
            if self.links:
                self.links[-1][1].append(value)


def fetch(url, timeout=25):
    request = Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; MoscowTransportRouteArchive/1.0; +https://www.moscowmap.ru/)',
                                   'Accept-Language': 'ru,en;q=0.8'})
    last = None
    for attempt in range(4):
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read().decode(response.headers.get_content_charset() or 'utf-8', errors='replace')
        except HTTPError as exc:
            last = exc
            if exc.code not in (429, 500, 502, 503, 504):
                break
        except (URLError, TimeoutError) as exc:
            last = exc
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f'Не удалось загрузить {url}: {last}')


def parse(html):
    page = Page()
    page.feed(html)
    text = re.sub(r'\n\s*\n+', '\n', ''.join(page.text))
    links = [(href, ' '.join(label)) for href, label in page.links]
    stops = []
    in_stops = False
    for line in text.splitlines():
        normalized = line.strip()
        if re.search(r'список остановок', normalized, re.I):
            in_stops = True
            continue
        if in_stops and re.search(r'^улицы по маршруту', normalized, re.I):
            break
        if in_stops:
            match = STOP_LINE.match(normalized)
            if match:
                stops.append({'sequence': int(match[1]), 'name': match[2].strip()})
    # MoscowMap embeds route map coordinates in page scripts. Keep only points
    # inside a broad Moscow bounding box, accepting either lon/lat ordering.
    points, seen = [], set()
    for a, b in COORD_PAIR.findall(html):
        x, y = float(a), float(b)
        if 36 <= x <= 39 and 54 <= y <= 57:
            point = [x, y]
        elif 54 <= x <= 57 and 36 <= y <= 39:
            point = [y, x]
        else:
            continue
        key = (round(point[0], 6), round(point[1], 6))
        if key not in seen:
            points.append(point)
            seen.add(key)
    source = unescape(html)
    for stop in stops:
        candidates = []
        name = unescape(stop['name'])
        for match in re.finditer(re.escape(name), source, re.I):
            left, right = max(0, match.start()-500), min(len(source), match.end()+500)
            for pair in COORD_PAIR.finditer(source, left, right):
                a, b = float(pair[1]), float(pair[2])
                if 36 <= a <= 39 and 54 <= b <= 57:
                    coord = [a, b]
                elif 54 <= a <= 57 and 36 <= b <= 39:
                    coord = [b, a]
                else:
                    continue
                candidates.append((abs(pair.start()-match.start()), coord))
        if candidates:
            stop['coordinates'] = min(candidates, key=lambda candidate: candidate[0])[1]
    return page, text, links, stops, points


def crawl(output, delay=0.4, limit=0):
    output.mkdir(parents=True, exist_ok=True)
    checkpoint = output / 'discovered_urls.txt'
    queue, seen, records = [INDEX], set(), {}
    if checkpoint.exists():
        for line in checkpoint.read_text(encoding='utf-8').splitlines():
            if line and line not in seen:
                queue.append(line)
    errors = []
    while queue and (not limit or len(records) < limit):
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            html = fetch(url)
            page, text, links, stops, points = parse(html)
            path = urlparse(url).path
            if ROUTE_PATH.match(path):
                title = ' '.join(page.h1).strip()
                slug = Path(path).stem
                category = path.strip('/').split('/')[1]
                route_number = title.split(' - ', 1)[0].strip() if title else slug
                if '№' in route_number:
                    route_number = route_number.split('№', 1)[1].strip()
                else:
                    words = route_number.split()
                    route_number = ' '.join(words[2:] if category == 'rechnoy-transport' else words[1:])
                route_id = f'{category}-{slug}'
                for stop in stops:
                    stop['id'] = f"{route_id}-{stop['sequence']}"
                    stop['direction'] = 0
                records[url] = {'id': route_id, 'number': route_number, 'title': title or slug,
                                'url': url, 'transport': category, 'stops': stops, 'coordinates': points}
                print(f'[{len(records)}] {route_number}: {len(stops)} остановок, {len(points)} точек')
            for href, _ in links:
                absolute = urljoin(url, href).split('#', 1)[0]
                p = urlparse(absolute)
                parts = p.path.strip('/').split('/')
                category_index = p.path.startswith('/marshruty-gorodskogo-transporta/') and len(parts) == 2 and parts[1].endswith('.html')
                moscow_index = p.path.startswith('/marshruty-gorodskogo-transporta/') and len(parts) == 3 and parts[2] in {'moscow', 'moscow.html'}
                if p.netloc in {'www.moscowmap.ru', 'moscowmap.ru'} and (ROUTE_PATH.match(p.path) or category_index or moscow_index):
                    if absolute not in seen and absolute not in queue:
                        queue.append(absolute)
            checkpoint.write_text('\n'.join(sorted(seen | set(queue))) + '\n', encoding='utf-8')
        except Exception as exc:  # Keep a useful partial archive and resume later.
            errors.append({'url': url, 'error': str(exc)})
            print(f'Ошибка: {url}: {exc}', file=sys.stderr)
        time.sleep(max(0, delay))
    routes = sorted(records.values(), key=lambda row: (row['number'].casefold(), row['id']))
    if not routes:
        (output / 'crawl_errors.json').write_text(json.dumps(errors, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'Не получено ни одной страницы маршрута; ошибок: {len(errors)}. Исправьте доступ к сайту и повторите запуск.')
        return
    with (output / 'routes.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['id', 'number', 'title', 'url', 'stop_count', 'shape_point_count'])
        writer.writeheader()
        for row in routes:
            writer.writerow({**{k: row[k] for k in ('id','number','title','url')},
                             'stop_count': len(row['stops']), 'shape_point_count': len(row['coordinates'])})
    with (output / 'stops.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['route_id','route_number','route_title','direction','sequence','stop_id','name','latitude','longitude','source_url'])
        writer.writeheader()
        for row in routes:
            for stop in row['stops']:
                point = stop.get('coordinates') or []
                writer.writerow({'route_id': row['id'], 'route_number': row['number'], 'route_title': row['title'],
                                 'direction': stop.get('direction', 0), 'sequence': stop['sequence'], 'stop_id': stop['id'], 'name': stop['name'],
                                 'latitude': point[1] if point else '', 'longitude': point[0] if point else '', 'source_url': row['url']})
    (output / 'routes.geojson').write_text(json.dumps({'type':'FeatureCollection','features':[
        {'type':'Feature','properties':{k: row[k] for k in ('id','number','title','url')},
         'geometry': {'type':'LineString','coordinates':row['coordinates']} if len(row['coordinates']) > 1 else None}
        for row in routes]}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (output / 'routes.json').write_text(json.dumps({'source': INDEX, 'fetchedAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'routes':routes}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (output / 'crawl_errors.json').write_text(json.dumps(errors, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Сохранено маршрутов: {len(routes)}; ошибок: {len(errors)}; каталог: {output}')


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--output', type=Path, default=Path('data/moscowmap'))
    cli.add_argument('--delay', type=float, default=0.4, help='пауза между запросами в секундах')
    cli.add_argument('--limit', type=int, default=0, help='ограничение числа страниц маршрутов; 0 = без лимита')
    args = cli.parse_args()
    crawl(args.output, args.delay, args.limit)

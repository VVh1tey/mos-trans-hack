#!/usr/bin/env python3
"""Crawl MoscowMap's public transport catalog into JSON, CSV, and GeoJSON."""
import argparse
import atexit
import csv
from html import unescape
from html.parser import HTMLParser
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

BASE = 'https://www.moscowmap.ru'
ROOT = '/marshruty-gorodskogo-transporta'
INDEX = BASE + ROOT + '/avtobusy.html'
START_PAGES = [BASE + ROOT + '.html', INDEX]
_browser_worker = None
COORD_PAIR = re.compile(r'(?<![\w.])(-?\d{2,3}\.\d{4,})\s*[,; ]\s*(-?\d{2,3}\.\d{4,})(?![\w.])')
STOP_LINE = re.compile(r'^\s*(\d+)\s*[.)\-\u2013\u2014\u2212\u2022\u00b7]?\s+(.+?)\s*$')


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
        if not value:
            return
        self.text.append(' ' + value + ' ')
        if self.in_h1:
            self.h1.append(value)
        if self.links:
            self.links[-1][1].append(value)


def fetch(url, timeout=25):
    # Use a regular browser UA; the previous project-specific UA caused some
    # edge filters to classify an otherwise ordinary page fetch as a bot.
    request = Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.7',
    })
    last = None
    for attempt in range(4):
        try:
            with urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or 'utf-8'
                return response.read().decode(charset, errors='replace')
        except HTTPError as exc:
            last = exc
            if exc.code not in (403, 429, 500, 502, 503, 504):
                break
        except (URLError, TimeoutError) as exc:
            last = exc
        if attempt < 3:
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f'Could not download {url}: {last}')


def fetch_rendered(url):
    """Fetch a JS-rendered page through the repo's installed Playwright."""
    global _browser_worker
    helper = Path(__file__).with_name('moscowmap_browser.mjs')
    if _browser_worker is None:
        if not helper.exists():
            raise RuntimeError(f'Playwright worker is missing: {helper}')
        _browser_worker = subprocess.Popen(
            ['node', str(helper)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, encoding='utf-8', cwd=Path(__file__).resolve().parents[1],
        )
        atexit.register(_browser_worker.terminate)
    _browser_worker.stdin.write(json.dumps({'url': url}, ensure_ascii=False) + '\n')
    _browser_worker.stdin.flush()
    try:
        line = _browser_worker.stdout.readline()
    except OSError as exc:
        raise RuntimeError('Could not read from the Playwright worker') from exc
    if not line:
        code = _browser_worker.poll()
        raise RuntimeError(f'Playwright worker exited without a response (exit code {code}); install frontend dependencies and Chromium.')
    result = json.loads(line)
    if result.get('error'):
        raise RuntimeError(f'Playwright could not render {url}: {result["error"]}')
    if result.get('status', 200) >= 400:
        raise RuntimeError(f'MoscowMap returned HTTP {result["status"]} in the browser for {url}')
    return result['html']


def normalize_coord(a, b):
    x, y = float(a), float(b)
    if 36 <= x <= 39 and 54 <= y <= 57:
        return [x, y]
    if 54 <= x <= 57 and 36 <= y <= 39:
        return [y, x]
    return None


def parse(html):
    page = Page()
    page.feed(html)
    text = re.sub(r'\n\s*\n+', '\n', ''.join(page.text))
    links = [(href, ' '.join(label)) for href, label in page.links]

    # Pages use both ordered lists and plain text for stop names. Search only
    # in the stop-list section, ending at the next route description section.
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines)
                  if re.search(r'\u0441\u043f\u0438\u0441\u043e\u043a\s+\u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043e\u043a', line, re.I)), None)
    stops = []
    if start is not None:
        for line in lines[start + 1:]:
            normalized = line.strip()
            if re.search(r'^\u0443\u043b\u0438\u0446\u044b\s+\u043f\u043e\s+\u043c\u0430\u0440\u0448\u0440\u0443\u0442\u0443', normalized, re.I):
                break
            match = STOP_LINE.match(normalized)
            if match:
                stops.append({'sequence': int(match[1]), 'name': match[2].strip()})

    points, seen = [], set()
    for a, b in COORD_PAIR.findall(html):
        point = normalize_coord(a, b)
        if point:
            key = (round(point[0], 6), round(point[1], 6))
            if key not in seen:
                points.append(point)
                seen.add(key)

    # Associate stop coordinates with nearby occurrences of their names.
    source = unescape(html)
    for stop in stops:
        candidates = []
        for match in re.finditer(re.escape(stop['name']), source, re.I):
            left, right = max(0, match.start() - 500), min(len(source), match.end() + 500)
            for pair in COORD_PAIR.finditer(source, left, right):
                point = normalize_coord(pair[1], pair[2])
                if point:
                    candidates.append((abs(pair.start() - match.start()), point))
        if candidates:
            stop['coordinates'] = min(candidates, key=lambda candidate: candidate[0])[1]
    return page, links, stops, points


def is_catalog_page(url):
    parsed = urlparse(url)
    host = parsed.netloc.lower().split(':', 1)[0]
    path = parsed.path.rstrip('/')
    return (host in {'www.moscowmap.ru', 'moscowmap.ru'}
            and path.startswith(ROOT) and path != ROOT)


def crawl(output, delay=0.4, limit=0):
    output.mkdir(parents=True, exist_ok=True)
    checkpoint = output / 'discovered_urls.txt'
    queue, seen, records = list(START_PAGES), set(), {}
    if checkpoint.exists():
        for line in checkpoint.read_text(encoding='utf-8').splitlines():
            if line and line not in queue:
                queue.append(line)
    errors, fetched_pages = [], 0
    while queue and (not limit or len(records) < limit):
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            try:
                html = fetch(url)
            except Exception as static_error:
                print(f'Static fetch failed for {url} ({static_error}); retrying with Playwright')
                html = fetch_rendered(url)
            else:
                _, initial_links, _, _ = parse(html)
                if not initial_links:
                    print(f'No static links in {url}; retrying with Playwright')
                    html = fetch_rendered(url)
            fetched_pages += 1
            page, links, stops, points = parse(html)
            path = urlparse(url).path
            parts = path.strip('/').split('/')
            # The root and category pages link to routes; route pages are
            # deeper HTML documents under the same catalog tree.
            if path.rstrip('/') != ROOT + '.html' and len(parts) >= 3:
                title = ' '.join(page.h1).strip()
                slug, category = Path(path).stem, parts[1]
                number = title.split(' - ', 1)[0].strip() if title else slug
                number = re.sub(r'^(?:\u0430\u0432\u0442\u043e\u0431\u0443\u0441|\u0442\u0440\u0430\u043c\u0432\u0430\u0439|\u0442\u0440\u043e\u043b\u043b\u0435\u0439\u0431\u0443\u0441|\u044d\u043b\u0435\u043a\u0442\u0440\u043e\u0431\u0443\u0441|\u043c\u0430\u0440\u0448\u0440\u0443\u0442\u043a\u0430|\u0440\u0435\u0447\u043d\u043e\u0439\s+\u0442\u0440\u0430\u043d\u0441\u043f\u043e\u0440\u0442)\s*\u2116?\s*', '', number, flags=re.I).strip()
                route_id = f'{category}-{slug}'
                for stop in stops:
                    stop['id'] = f'{route_id}-{stop["sequence"]}'
                    stop['direction'] = 0
                records[url] = {
                    'id': route_id, 'number': number, 'title': title or slug,
                    'url': url, 'transport': category, 'stops': stops,
                    'coordinates': points,
                }
                print(f'[{len(records)}] {number}: {len(stops)} stops, {len(points)} shape points')

            catalog_links = []
            for href, _ in links:
                # Query parameters can select the catalog's number-range tabs
                # or reveal the full route list, so retain them while removing
                # only the in-page fragment.
                absolute = urljoin(url, href).split('#', 1)[0]
                if is_catalog_page(absolute):
                    catalog_links.append(absolute)
                    if absolute not in seen and absolute not in queue:
                        queue.append(absolute)
            print(f'Fetched {url}: title={" ".join(page.h1)!r}, links={len(links)}, catalog links={len(catalog_links)}')
            # Save pending URLs (rather than already failed/visited URLs) so
            # a resumed crawl does not silently skip pages that failed.
            checkpoint.write_text('\n'.join(queue) + ('\n' if queue else ''), encoding='utf-8')
        except Exception as exc:
            errors.append({'url': url, 'error': str(exc)})
            print(f'Error: {url}: {exc}', file=sys.stderr)
        time.sleep(max(0, delay))

    routes = sorted(records.values(), key=lambda row: (row['number'].casefold(), row['id']))
    (output / 'crawl_errors.json').write_text(json.dumps(errors, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if not routes:
        print(f'No routes found: fetched {fetched_pages} pages, errors {len(errors)}. Check catalog URL and page markup.')
        return

    with (output / 'routes.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['id', 'number', 'title', 'url', 'stop_count', 'shape_point_count'])
        writer.writeheader()
        for row in routes:
            writer.writerow({**{key: row[key] for key in ('id', 'number', 'title', 'url')},
                             'stop_count': len(row['stops']), 'shape_point_count': len(row['coordinates'])})
    with (output / 'stops.csv').open('w', encoding='utf-8-sig', newline='') as f:
        fields = ['route_id', 'route_number', 'route_title', 'direction', 'sequence', 'stop_id', 'name', 'latitude', 'longitude', 'source_url']
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in routes:
            for stop in row['stops']:
                point = stop.get('coordinates') or []
                writer.writerow({'route_id': row['id'], 'route_number': row['number'], 'route_title': row['title'],
                                 'direction': stop.get('direction', 0), 'sequence': stop['sequence'], 'stop_id': stop['id'],
                                 'name': stop['name'], 'latitude': point[1] if point else '',
                                 'longitude': point[0] if point else '', 'source_url': row['url']})
    features = []
    for row in routes:
        features.append({'type': 'Feature', 'properties': {key: row[key] for key in ('id', 'number', 'title', 'url')},
                         'geometry': {'type': 'LineString', 'coordinates': row['coordinates']} if len(row['coordinates']) > 1 else None})
    (output / 'routes.geojson').write_text(json.dumps({'type': 'FeatureCollection', 'features': features}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    archive = {'source': INDEX, 'fetchedAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'routes': routes}
    (output / 'routes.json').write_text(json.dumps(archive, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Saved {len(routes)} routes; fetched {fetched_pages} pages; errors {len(errors)}; output: {output}')


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--output', type=Path, default=Path('data/moscowmap'))
    cli.add_argument('--delay', type=float, default=0.4, help='seconds between requests')
    cli.add_argument('--limit', type=int, default=0, help='maximum number of route pages; 0 means no limit')
    args = cli.parse_args()
    crawl(args.output, args.delay, args.limit)

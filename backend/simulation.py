"""Historical test playback control and snapshot facade."""
import json
import os
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener
from replay import Replay

EMULATOR_URL = os.getenv('EMULATOR_URL', 'http://127.0.0.1:18081')
INGEST_URL = os.getenv('INGEST_URL', 'http://127.0.0.1:9101')
HTTP = build_opener(ProxyHandler({}))


def request(url, body=None):
    req = Request(url, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    with HTTP.open(req, timeout=3) as response:
        content = response.read()
        return json.loads(content) if content else {}


REPLAY = Replay(os.getenv('DATASET_DIR', str(Path(__file__).resolve().parents[1] / 'dataset')),
                os.getenv('NDTP_TARGET_HOST', '127.0.0.1'), int(os.getenv('NDTP_TARGET_PORT', '9201')),
                request, INGEST_URL, os.getenv('ML_URL', 'http://127.0.0.1:8001'))


def status():
    errors = []
    try:
        telemetry = request(INGEST_URL + '/telemetry')
    except (URLError, TimeoutError, OSError, ValueError):
        telemetry = None
        errors.append('Нет связи с приёмником NDTP. Проверьте сервис ingest.')
    try:
        result = REPLAY.snapshot(telemetry)
        result['errors'].extend(errors)
        return result
    except (OSError, ValueError, KeyError) as exc:
        return {'source': 'test', 'available': False, 'running': None, 'telemetry': None,
                'ingestAvailable': telemetry is not None, 'errors': [f'Не удалось загрузить полные файлы test: {exc}']}


def control(action, speed=None):
    if action not in ('start', 'stop', 'reset', 'speed'):
        raise ValueError('action must be start, stop, reset or speed')
    if action in ('start', 'reset'):
        # The original generator remains available, but must not mix into replay.
        try:
            config = request(EMULATOR_URL + '/api/config')
        except (URLError, TimeoutError, OSError):
            config = None
        if config and config.get('units'):
            request(EMULATOR_URL + '/api/config', {**config, 'units': []})
    REPLAY.control(action, speed)
    return status()

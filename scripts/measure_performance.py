"""Small sequential HTTP/decoder benchmark, not a capacity or end-to-end test."""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import sys
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from ndtp import Decoder, encode_navigation


def main():
    body = json.dumps(dict(sample_id='performance-check', cur_dev_s=120)).encode()
    results = {}
    for name, url in [('ml_http', 'http://ml:8001/predict'), ('backend_http', 'http://backend:8000/api/predict')]:
        durations = []
        for i in range(110):
            started = time.perf_counter()
            with urlopen(Request(url, data=body, headers={'Content-Type': 'application/json'}), timeout=10) as response:
                result = json.load(response)
                assert math.isfinite(result['prediction'])
            if i >= 10:
                durations.append(time.perf_counter() - started)
        ordered = sorted(durations)
        results[name] = dict(requests=len(ordered), errors=0, p50_ms=ordered[49]*1000,
                             p95_ms=ordered[94]*1000, max_ms=max(ordered)*1000,
                             sequential_rps=len(ordered)/sum(ordered), model=result['model'])
    frame = encode_navigation(dict(unitId=1, eventTime=100, coordinates=[37.6, 55.7],
                                   locationValid=True, speedKmh=20, heading=90, altitude=100), 1)
    decoder = Decoder()
    started = time.perf_counter()
    count = sum(len(decoder.feed(frame*100)) for _ in range(200))
    elapsed = time.perf_counter()-started
    results['decoder_only'] = dict(frames=count, errors=decoder.errors, seconds=elapsed, frames_per_second=count/elapsed)
    cpu = next((line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')), 'unknown')
    report = dict(measured_at=datetime.now(timezone.utc).isoformat(), platform=platform.platform(),
                  python=platform.python_version(), visible_cpus=os.cpu_count(), cpu=cpu,
                  concurrency=1, warmup_per_endpoint=10, input={'cur_dev_s':120}, results=results,
                  limitations='Local Docker network; sequential warm HTTP, partial features; decoder in memory without TCP/storage/map. Not a capacity or end-to-end benchmark.')
    (ROOT/'docs/performance.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

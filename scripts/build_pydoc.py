"""Generate checked-in PyDoc HTML without starting any service."""

import importlib
from pathlib import Path
import pydoc
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs' / 'pydoc'
MODULES = {
    'backend': ('app', 'dashboard', 'ingest', 'ndtp', 'replay', 'simulation'),
    'ml': ('experiments.baseline', 'experiments.mean_residual',
           'experiments.catboost_clean', 'experiments.catboost_timeseries',
           'experiments.catboost_context', 'experiments.catboost_telemetry'),
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    links = []
    for directory, names in MODULES.items():
        sys.path.insert(0, str(ROOT / directory))
        try:
            for name in names:
                module = importlib.import_module(name)
                file_name = f'{directory}-{name.replace(".", "-")}.html'
                html = pydoc.HTMLDoc().document(module)
                (OUT / file_name).write_text('\n'.join(line.rstrip() for line in html.splitlines()) + '\n', encoding='utf-8')
                links.append(f'<li><a href="{file_name}">{directory}/{name.replace(".", "/")}.py</a></li>')
        finally:
            sys.path.pop(0)
    (OUT / 'index.html').write_text('<!doctype html><html lang="ru"><meta charset="utf-8"><title>PyDoc</title><h1>Документация Python-модулей</h1><ul>' + ''.join(links) + '</ul></html>', encoding='utf-8')
    print(f'Generated {len(links)} modules in {OUT}')


if __name__ == '__main__':
    main()

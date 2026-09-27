"""Build HTML API documentation; run in the ML Docker image for dependencies."""
import importlib
import os
from pathlib import Path
import pydoc
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs' / 'pydoc'
MODULES = {
    'backend': ('app', 'dashboard', 'ingest', 'ndtp', 'replay', 'simulation'),
    'ml': ('service', 'experiments.catboost_robust', 'experiments.catboost_context'),
}


def main():
    os.environ.setdefault('RUNS_DIR', str(ROOT / 'runs'))
    OUT.mkdir(parents=True, exist_ok=True)
    links = []
    for directory, names in MODULES.items():
        sys.path.insert(0, str(ROOT / directory))
        try:
            for name in names:
                module = importlib.import_module(name)
                filename = f'{directory}-{name.replace(".", "-")}.html'
                html = pydoc.HTMLDoc().document(module)
                (OUT / filename).write_text('\n'.join(line.rstrip() for line in html.splitlines()) + '\n', encoding='utf-8')
                links.append(f'<li><a href="{filename}">{directory}/{name.replace(".", "/")}.py</a></li>')
        finally:
            sys.path.pop(0)
    (OUT / 'index.html').write_text('<!doctype html><html lang="ru"><meta charset="utf-8">'
        '<title>PyDoc</title><h1>Документация Python-модулей</h1><ul>' + ''.join(links) + '</ul></html>\n', encoding='utf-8')
    print(f'Generated {len(links)} modules in {OUT}')


if __name__ == '__main__':
    main()

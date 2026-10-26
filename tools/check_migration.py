#!/usr/bin/env python3
"""Check module IDs and that module dependencies are known and acyclic."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.harness import ROOT


def validate(manifest):
    modules = manifest['modules']
    ids = [module['id'] for module in modules]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate module IDs')
    known = set(ids)
    for module in modules:
        if not set(module['depends_on']) <= known:
            raise ValueError(f'{module["id"]}: unknown prerequisite')
    done, waves = set(), []
    while len(done) != len(modules):
        ready = [m['id'] for m in modules if m['id'] not in done and set(m['depends_on']) <= done]
        if not ready:
            raise ValueError('Migration dependency cycle')
        waves.append(ready)
        done.update(ready)
    return waves


def main():
    manifest = json.loads((ROOT / 'migration/modules.json').read_text())
    waves = validate(manifest)
    print(f'{len(manifest["modules"])} modules; dependencies resolve.')
    for number, wave in enumerate(waves):
        print(f'Wave {number}: {", ".join(wave)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""Check module dependencies and that no two modules patch the same paths."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.harness import ROOT


def overlap(left, right):
    a, b = Path(left), Path(right)
    return a == b or a in b.parents or b in a.parents


def frozen_target_owners(entry):
    """Bind every byte-frozen patch destination to exactly one current owner."""
    targets = entry.get('upstream_paths', [])
    if ('target_owner' in entry) == ('target_owners' in entry):
        raise ValueError('Invalid frozen overlay owner schema')
    owners = entry.get('target_owners') if 'target_owners' in entry else {
        target: entry['target_owner'] for target in targets}
    if (not isinstance(owners, dict) or len(set(targets)) != len(targets)
            or set(owners) != set(targets) or not owners
            or any(not isinstance(owner, str) or not owner for owner in owners.values())):
        raise ValueError('Invalid frozen overlay destination owners')
    return owners


def validate(manifest):
    modules = manifest['modules']
    ids = [module['id'] for module in modules]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate module IDs')
    known = set(ids)
    for module in modules:
        if not set(module['depends_on']) <= known:
            raise ValueError(f'{module["id"]}: unknown prerequisite')
        for kind in ['owned_paths', 'upstream_patch_targets']:
            for path in module[kind]:
                if Path(path).is_absolute() or '..' in Path(path).parts:
                    raise ValueError(f'{module["id"]}: unsafe reserved path {path}')
    for index, left in enumerate(modules):
        for right in modules[index + 1:]:
            for kind in ['owned_paths', 'upstream_patch_targets']:
                for a in left[kind]:
                    for b in right[kind]:
                        if overlap(a, b):
                            raise ValueError(f'{left["id"]} / {right["id"]}: conflicting {kind}: {a} / {b}')
    by_id = {module['id']: module for module in modules}
    for module in modules:
        seen = set()
        for entry in module.get('frozen_upstream_patches', []):
            path = entry.get('path', '')
            digest = entry.get('sha256', '')
            owners = frozen_target_owners(entry)
            targets = entry.get('upstream_paths', [])
            if (not path or Path(path).is_absolute() or '..' in Path(path).parts or path in seen
                    or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest)
                    or any(owner not in by_id for owner in owners.values())
                    or all(owner == module['id'] for owner in owners.values()) or not targets
                    or not any(path.startswith(prefix.rstrip('/') + '/') for prefix in module['owned_paths']
                               if prefix.startswith('migration/patches/'))):
                raise ValueError(f'{module["id"]}: invalid frozen overlay contract')
            seen.add(path)
            for target, owner_id in owners.items():
                owner = by_id[owner_id]
                if (Path(target).is_absolute() or '..' in Path(target).parts or target.endswith('/')
                        or not any(target == reserved or target.startswith(reserved.rstrip('/') + '/')
                                   for reserved in owner['upstream_patch_targets'])):
                    raise ValueError(f'{module["id"]}: frozen overlay has no mutable target owner: {target}')
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
    print(f'{len(manifest["modules"])} modules; no overlapping owned paths or upstream patch targets.')
    for number, wave in enumerate(waves):
        print(f'Wave {number}: {", ".join(wave)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

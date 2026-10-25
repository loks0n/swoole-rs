"""Apply a buffer patch to a scratch upstream tree after checking it against the module manifest."""
import hashlib
import json
from pathlib import Path
import shlex
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.build_hybrid import apply_patch_verified


def apply_module_patch(tree, patch, *, allow_override=False):
    manifest = ROOT/'migration/patches/buffer/manifest.json'
    entries = json.loads(manifest.read_text())['patches']
    patch = Path(patch).resolve(strict=True)
    data = patch.read_bytes()
    targets = []
    old_files, new_files = [], []
    for line in data.decode().splitlines():
        if line.startswith('diff --git '):
            fields = shlex.split(line)
            if len(fields) != 4 or not fields[2].startswith('a/') or fields[3] != 'b/'+fields[2][2:]:
                raise ValueError('M01 patch requires explicit unchanged file destinations')
            targets.append(fields[2][2:])
        elif line.startswith('--- '):
            old_files.append(line[4:])
        elif line.startswith('+++ '):
            new_files.append(line[4:])
    if not targets or len(set(targets)) != len(targets):
        raise ValueError('M01 patch requires unique explicit Git-format destinations')
    if old_files != ['a/'+name for name in targets] or new_files != ['b/'+name for name in targets]:
        raise ValueError('M01 patch file headers differ from declared Git destinations')
    entry = next((entry for entry in entries if (manifest.parent/entry['path']).resolve() == patch), None)
    if entry is not None:
        if set(targets) != set(entry['upstream_paths']):
            raise ValueError('Committed M01 destinations differ from manifest')
        expected = entry['sha256']
        authority = 'committed-module-manifest'
    else:
        allowed = {name for entry in entries for name in entry['upstream_paths']}
        if not allow_override or not set(targets) <= allowed:
            raise ValueError('Explicit private M01 override must stay within declared module destinations')
        expected = hashlib.sha256(data).hexdigest()
        authority = 'explicit-private-override-not-manifest-qualified'
    proof = apply_patch_verified(tree, patch, targets, expected)
    return dict(authority=authority, patch_path=str(patch), destinations=targets, **proof)

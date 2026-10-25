"""Stage current utility overlays with manifest checks and changed-file evidence."""
import json
from pathlib import Path

from tools.build_hybrid import apply_patch_verified


def apply_owned(source, patch):
    patch = Path(patch)
    manifest = json.loads((patch.parent / 'manifest.json').read_text())
    entries = [row for row in manifest['patches'] if row['path'] == patch.name]
    if len(entries) != 1:
        raise ValueError('Utility patch must occur exactly once in its manifest')
    entry = entries[0]
    return apply_patch_verified(source, patch, entry['upstream_paths'], entry['sha256'])

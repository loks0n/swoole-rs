"""Exact pinned Swoole PHP8.5 expectation selection, without its custom runner."""
import hashlib
import re

KINDS = ('EXPECT', 'EXPECTF', 'EXPECTREGEX')


def select(data, php_version_id):
    if not isinstance(php_version_id, int) or php_version_id < 50000:
        raise ValueError('Require actual PHP_VERSION_ID')
    markers = list(re.finditer(rb'^--([A-Z][A-Z0-9_]*)--(?:\r?\n|$)', data, re.M))
    if not markers or markers[0].start() != 0:
        raise ValueError('Malformed PHPT section prefix')
    parts = {}
    for index, marker in enumerate(markers):
        name = marker.group(1).decode('ascii')
        if name in parts:
            raise ValueError('Duplicate PHPT section: ' + name)
        end = markers[index + 1].start() if index + 1 < len(markers) else len(data)
        parts[name] = (data[marker.start():marker.end()], data[marker.end():end])
    conditional = [kind + '_85' for kind in KINDS if kind + '_85' in parts]
    selected = {kind: kind + '_85' if php_version_id >= 80500 and kind + '_85' in parts else kind
                for kind in KINDS if kind in parts or php_version_id >= 80500 and kind + '_85' in parts}
    if len(selected) != 1:
        raise ValueError('Require one active original expectation kind')
    chunks = []
    for name, (marker, body) in parts.items():
        if name in conditional:
            base = name.removesuffix('_85')
            if php_version_id >= 80500 and base not in parts:
                chunks.append(marker.replace(b'_85', b'') + body)
        elif name in selected:
            chunks.append(marker + parts[selected[name]][1])
        else:
            chunks.append(marker + body)
    adapted = b''.join(chunks)
    sha = lambda value: hashlib.sha256(value).hexdigest()
    return adapted, {'adapter': 'pinned-swoole-php85-expectations-v1', 'php_version_id': php_version_id,
                     'original_sha256': sha(data), 'adapted_sha256': sha(adapted),
                     'selected_section': next(iter(selected.values())),
                     'selected_body_sha256': sha(parts[next(iter(selected.values()))][1]),
                     'conditional_sections': conditional,
                     'protected_sections_sha256': {name: sha(marker + body) for name, (marker, body) in parts.items()
                         if name not in KINDS and name not in conditional}}

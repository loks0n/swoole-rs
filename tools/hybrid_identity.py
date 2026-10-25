"""Verify selected first-party source inputs against an immutable hybrid receipt.

Registry/std contents are outside this attestation; their lock/compiler/archive
identities remain separate. Native reference provenance is not inferred here.
"""
import hashlib
import json
from pathlib import Path
import subprocess
from tools.harness import ROOT
from tools.build_upstream import COMMIT


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def attest(manifest_path, archive, identity, source_ref, expected_bit, *, root=ROOT):
    manifest_path, archive = Path(manifest_path), Path(archive)
    manifest = json.loads(manifest_path.read_text())
    inputs = manifest['inputs']
    if (manifest.get('build_mode') != 'immutable' or inputs['upstream_commit'] != COMMIT
            or identity['sha256'] != manifest['extension_sha256']
            or identity['rust_feature_bits'] != manifest['migrated_feature_bits']
            or not identity['rust_feature_bits'] & expected_bit):
        raise ValueError('Selected immutable extension/configuration identity differs')
    if sha(archive) != inputs['rust_archive_sha256']:
        raise ValueError('Selected archive differs from compiled build receipt')
    artifact = manifest['rust_compilation']['artifact']
    if (artifact['target']['kind'] != ['staticlib'] or artifact['profile']['opt_level'] != '3'
            or artifact['profile']['test'] or artifact['profile']['debug_assertions']):
        raise ValueError('Actual Cargo artifact is not the production static library')
    sources = inputs['rust_sources_sha256']
    if not sources or not inputs['headers_sha256'] or not inputs['patches']:
        raise ValueError('Missing selected first-party source attestation')
    expected = dict(sources)
    expected.update(inputs['headers_sha256'])
    expected.update({item['path']: item['sha256'] for item in inputs['patches']})
    expected.update({'tools/build_hybrid.py': inputs['builder_sha256'],
                     'tools/build_upstream.py': inputs['php_builder_sha256']})
    if 'cache_helper_sha256' in inputs:
        expected['tools/shared_cache.py'] = inputs['cache_helper_sha256']
    source = subprocess.check_output(['git', 'rev-parse', '--verify', '--end-of-options',
                                      source_ref + '^{commit}'], cwd=root, text=True).strip()
    for relative, digest in expected.items():
        path = Path(relative)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('Source receipt contains an invalid relative path')
        content = subprocess.check_output(['git', 'show', source + ':' + relative], cwd=root)
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError('Frozen source differs from compiled input: ' + relative)
    return {'record_type': 'selected_first_party_build_inputs', 'source_ref': source,
            'manifest_sha256': sha(manifest_path), 'archive_sha256': sha(archive),
            'extension_sha256': identity['sha256'], 'verified_inputs': len(expected),
            'scope': __doc__, 'helper_sha256': sha(__file__)}

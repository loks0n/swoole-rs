#!/usr/bin/env python3
"""Attested native/PHP consumers for the selected HTTP bindings source and build."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import parse_engines, write_report
from tools.build_upstream import COMMIT
ROOT = Path(__file__).resolve().parents[3]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--source-ref', required=True, help='Explicit immutable source commit, not HEAD')
    parser.add_argument('--build-manifest', action='append', required=True, help='Candidate NAME=manifest path; native control has observed identity only')
    parser.add_argument('--source-receipt', action='append', default=[], help='Candidate NAME=receipt path, with source_commit/source_inputs/inputs_unchanged/returncode')
    parser.add_argument('--archive', action='append', default=[], help='Candidate NAME=exact linked archive path; defaults to adjacent exported archive')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    engines = parse_engines(args.engine, args.php, args.php_extension)
    if len(engines) < 2 or engines[0].name != 'upstream':
        parser.error('First engine upstream=PATH plus candidate engine(s) required')
    manifests = dict(value.split('=', 1) for value in args.build_manifest)
    receipts = dict(value.split('=', 1) for value in args.source_receipt)
    archives = dict(value.split('=', 1) for value in args.archive)
    report = {'scope': __doc__, 'source_ref': args.source_ref, 'engines': [], 'attestations': [],
              'checks': [], 'errors': [], 'passed': False,
              'limitations': 'Small real caller corpus, not complete original inventories, lifetime/bailout proof or performance. Native control build identity is observed, not independently attested.'}
    try:
        if len(args.source_ref) != 40 or any(c not in '0123456789abcdef' for c in args.source_ref):
            raise ValueError('source-ref must be a full lowercase hexadecimal commit')
        source = subprocess.check_output(['git', 'rev-parse', args.source_ref + '^{commit}'], cwd=ROOT, text=True).strip()
        assert source == args.source_ref
        for engine in engines:
            metadata = engine.metadata()
            report['engines'].append(metadata)
            if engine.name == 'upstream':
                assert not metadata['rust_feature_bits'], metadata
                continue
            manifest_path = Path(manifests.pop(engine.name)).resolve()
            manifest = json.loads(manifest_path.read_text())
            inputs = manifest['inputs']
            assert manifest['extension_sha256'] == metadata['sha256']
            assert manifest['migrated_feature_bits'] == metadata['rust_feature_bits']
            assert metadata['rust_feature_bits'] & 2097152 and 'httpbindings' in inputs['modules']
            assert inputs['backend'] == 'rust' and '--enable-swoole-rs-httpbindings' in inputs['effective_configure']
            assert inputs['upstream_commit'] == COMMIT
            expected_paths = {f'ext-src/swoole_http_{name}.cc' for name in ['cookie', 'request', 'response', 'server', 'server_coro']}
            selected_patches = [p for p in inputs['patches'] if p['path'].startswith('migration/patches/httpbindings/')]
            assert {d for p in selected_patches for d in p['upstream_paths']} == expected_paths
            receipt_identity = {}
            identities = dict(inputs.get('rust_sources_sha256') or {})
            if identities:
                compilation = manifest['rust_compilation']
                assert '--release' in compilation['command']
                artifact = compilation['artifact']
                assert artifact['target']['name'] == 'swoole_rs_ffi'
                assert artifact['profile']['opt_level'] != '0' and not artifact['profile']['test']
            if engine.name in receipts:
                receipt_path = Path(receipts.pop(engine.name)).resolve()
                receipt = json.loads(receipt_path.read_text())
                assert receipt['source_commit'] == source and receipt['inputs_unchanged'] and receipt['returncode'] == 0
                for path, sha in receipt['source_inputs'].items():
                    if path in identities:
                        assert identities[path] == sha, path
                    identities[path] = sha
                receipt_identity = {'source_receipt': str(receipt_path)}
            if not identities:
                raise ValueError('Legacy manifest requires a matching --source-receipt; no Rust source attestation available')
            required_rust = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', source, 'crates/httpbindings'], cwd=ROOT, text=True).splitlines()
            assert all(path in identities for path in required_rust if path.endswith(('.rs', 'Cargo.toml')))
            assert all(path in identities for path in ['Cargo.toml', 'Cargo.lock', 'crates/ffi/Cargo.toml', 'crates/ffi/src/lib.rs'])
            identities.update({p['path']: p['sha256'] for p in selected_patches})
            identities.update({p: sha for p, sha in inputs['headers_sha256'].items() if p.startswith('native/httpbindings/')})
            assert identities
            for path, sha in identities.items():
                selected = subprocess.check_output(['git', 'show', f'{source}:{path}'], cwd=ROOT)
                assert hashlib.sha256(selected).hexdigest() == sha, path
            # The extension is matched to its exact linked archive; this is not
            # replaced with a source checkout's newer Cargo output.
            archive = Path(archives.pop(engine.name)).resolve() if engine.name in archives else manifest_path.with_name('libswoole_rs_ffi.a')
            assert digest(archive) == inputs['rust_archive_sha256']
            report['attestations'].append({'engine': engine.name, 'build_manifest': str(manifest_path),
                **receipt_identity, 'archive': str(archive), 'rust_compilation': manifest.get('rust_compilation'),
                'configuration': inputs['effective_configure'],
                'native_halfclose_correction': inputs['fix_halfclose'], 'modules': inputs['modules']})
        assert not manifests and not receipts and not archives, (manifests, receipts, archives)
        common = [arg for engine in engines for arg in ['--engine', f'{engine.name}={engine.extension}']]
        common += [arg for extension in args.php_extension for arg in ['--php-extension', extension]]
        for name in ['cookie_php', 'server_php', 'request_php', 'compression_php', 'settings_php', 'emission_php', 'settings_fatal', 'file_php']:
            output = args.output.with_name(args.output.stem + '-' + name + '.json')
            command = [sys.executable, str(Path(__file__).with_name(name + '.py')), *common, '--php', args.php, '--output', str(output)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=180)
            row = {'name': name, 'command': command, 'returncode': result.returncode,
                   'stdout': result.stdout, 'stderr': result.stderr, 'output': str(output)}
            report['checks'].append(row)
        report['passed'] = all(row['returncode'] == 0 for row in report['checks'])
    except Exception as error:
        report['errors'].append(f'{type(error).__name__}: {error}')
    write_report(args.output, report)
    print(json.dumps({'passed': report['passed'], 'checks': len(report['checks']), 'errors': report['errors']}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())

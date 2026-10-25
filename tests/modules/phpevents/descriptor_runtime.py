#!/usr/bin/env python3
"""Attested actual PHP startup and ordinary scalar/plain-file descriptor consumers.

No Event operations, reactor, callbacks, network, IPC or stopped profiles.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.build_upstream import require_build_space
from tools.harness import Engine, parse_engines, run_isolated, write_report
from tools.hybrid_identity import attest

builder_path = ROOT / 'tests/modules/phphelpers/entrypoint.py'
spec = importlib.util.spec_from_file_location('native_helper_builder', builder_path)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
BIT = 67108864


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


CALLERS = {
    'catalog': ('swr_v1_phpevents_alias', 'swr_v1_phpevents_catalogue'),
    'descriptor': 'swr_v1_phpevents_fd',
    'stream': 'swr_v1_phpevents_stream',
    'passive_query': 'swr_v1_phpevents_query',
}


def require_callers(patches, read_source):
    """Refuse same-bit older artifacts missing this fixture's actual callers."""
    rows = [row for row in patches if 'ext-src/swoole_event.cc' in row['upstream_paths']]
    if not rows:
        raise ValueError('Missing attested Event caller overlay')
    additions = []
    identities = {}
    for row in rows:
        path = Path(row['path'])
        if path.is_absolute() or '..' in path.parts or row['upstream_paths'] != ['ext-src/swoole_event.cc']:
            raise ValueError('Invalid isolated Event overlay identity')
        content = read_source(row['path'])
        digest = hashlib.sha256(content).hexdigest()
        if digest != row['sha256']:
            raise ValueError('Attested Event overlay source differs')
        identities[row['path']] = digest
        additions.extend(line for line in content.decode().splitlines() if line.startswith('+') and not line.startswith('+++'))
    present = {name: any(symbol + '(' in line for line in additions for symbol in (symbols if isinstance(symbols, tuple) else (symbols,))) for name, symbols in CALLERS.items()}
    if not all(present.values()):
        raise ValueError('Selected source lacks current fixture Rust callers: ' + ', '.join(name for name, ok in present.items() if not ok))
    return dict(required_rust_callers=CALLERS, matched=present, overlay_sha256=identities)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk-report', type=Path, required=True)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--engine', action='append')
    parser.add_argument('--source-ref')
    parser.add_argument('--build-manifest', type=Path)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.prepare_only and not all((args.engine, args.source_ref, args.build_manifest, args.archive)):
        parser.error('Runtime requires native/selected engines, source-ref, manifest and archive')
    work = args.output.resolve().parent / ('phpevents-descriptors-' + uuid.uuid4().hex)
    work.mkdir(parents=True)
    fixtures = {name: Path(__file__).with_name('descriptor_' + name)
                for name in ('entrypoint.cc', 'entrypoint.php')}
    report = dict(passed=False, scope=__doc__, work=str(work), results=[], engines=[], metadata_commands=[],
                  preparation_only=args.prepare_only, runtime_executed=False,
                  fixture_sha256={name: sha(path) for name, path in fixtures.items()},
                  measurement_performed=False)
    try:
        for name, path in fixtures.items():
            shutil.copy2(path, work / name)
        helper = builder.build_helper(args.sdk_report, work, report)
        report['helper_sha256'] = sha(helper)
        symbols = run_isolated(['nm', '-u', str(helper)], timeout=30)
        report['helper_imports'] = dict(exit=symbols.returncode, stdout=symbols.stdout, stderr=symbols.stderr)
        if symbols.returncode or any(name not in symbols.stdout for name in (
                'php_swoole_convert_to_fd', 'php_swoole_convert_to_fd_ex')):
            raise ValueError('Actual native descriptor ABI consumers missing')
        if not args.prepare_only:
            copies = []
            for index, engine in enumerate(parse_engines(args.engine, args.php, args.php_extension)):
                require_build_space(work)
                copied = work / ('engine-' + str(index) + '.so')
                expected = sha(engine.extension)
                shutil.copy2(engine.extension, copied)
                if sha(copied) != expected:
                    raise ValueError('Extension copy differs')
                copies.append(Engine(engine.name, copied, engine.php, engine.php_extensions))
            for engine in copies:
                probe = "if (!extension_loaded('swoole')) {fwrite(STDERR,'swoole missing');exit(1);} echo json_encode(['php'=>PHP_VERSION,'swoole'=>phpversion('swoole'),'zts'=>PHP_ZTS,'rust_feature_bits'=>defined('SWOOLE_RS_FEATURE_BITS')?SWOOLE_RS_FEATURE_BITS:0]);"
                result = run_isolated(engine.command('-r', probe), timeout=10, cwd=work)
                report['metadata_commands'].append(dict(engine=engine.name, command=engine.command('-r', probe), exit=result.returncode, stdout=result.stdout, stderr=result.stderr))
                if result.returncode or result.stderr:
                    raise ValueError('Metadata probe failed or warned; retain initial output')
                identity = json.loads(result.stdout)
                identity.update(name=engine.name, extension=str(engine.extension), sha256=sha(engine.extension), php_extensions=list(engine.php_extensions))
                if identity['php'] != report['helper_compilation']['sdk_php']:
                    raise ValueError('PHP SDK and actual engine differ')
                report['engines'].append(identity)
            selected = [row for row in report['engines'] if row['rust_feature_bits'] & BIT]
            if len(selected) != 1 or len(copies) != 2 or sum(row['rust_feature_bits'] == 0 for row in report['engines']) != 1:
                raise ValueError('Require one actual M28 and one native control')
            report['source_attestation'] = attest(args.build_manifest, args.archive, selected[0], args.source_ref, BIT)
            source = report['source_attestation']['source_ref']
            inputs = json.loads(args.build_manifest.read_text())['inputs']
            report['caller_source_identity'] = require_callers(inputs['patches'], lambda path: subprocess.check_output(['git', 'show', source + ':' + path], cwd=ROOT))
            for index, (engine, identity) in enumerate(zip(copies, report['engines'])):
                command = engine.command('-d', 'extension=' + str(helper), str(work / 'entrypoint.php'), str(work / ('private-' + str(index))))
                result = run_isolated(command, timeout=30, cwd=work)
                report['runtime_executed'] = True
                row = dict(engine=engine.name, command=command, exit=result.returncode,
                           stdout=result.stdout, stderr=result.stderr, passed=False,
                           extension_sha256_after=sha(engine.extension))
                report['results'].append(row)
                if not result.returncode and not result.stderr and row['extension_sha256_after'] == identity['sha256']:
                    row['summary'] = json.loads(result.stdout)
                    row['passed'] = len(row['summary']['catalog']) == 11
                write_report(args.output, report)
                if result.returncode < 0:
                    report['stopped_on_signal'] = True
                    report['not_run_engines'] = [item.name for item in copies[index + 1:]]
                    break
            if len(report['results']) != 2 or not all(row['passed'] for row in report['results']):
                raise ValueError('Descriptor consumer failed; retain first outputs without retry')
            if len({json.dumps(row['summary'], sort_keys=True) for row in report['results']}) != 1:
                raise ValueError('Native/selected descriptor summaries differ')
            receipt = report['source_attestation']
            if sha(args.build_manifest) != receipt['manifest_sha256'] or sha(args.archive) != receipt['archive_sha256']:
                raise ValueError('Selected build inputs changed')
        if any(sha(path) != report['fixture_sha256'][name] or sha(work / name) != report['fixture_sha256'][name]
               for name, path in fixtures.items()):
            raise ValueError('Fixture changed')
        if any(sha(path) != digest for path, digest in report['helper_compilation']['dependencies_sha256'].items()):
            raise ValueError('Consumed SDK changed')
        if sha(helper) != report['helper_sha256']:
            raise ValueError('Helper changed')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
    write_report(args.output, report)
    print(json.dumps({key: report.get(key) for key in ('passed', 'error', 'preparation_only', 'runtime_executed', 'work')}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())

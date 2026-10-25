#!/usr/bin/env python3
"""Copy immutable PHP artifacts and verify collection workloads without clocks."""
import argparse
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import uuid
from gate import ROOT, sha
from tools.harness import Engine, run_isolated, write_report
from tools.build_upstream import require_build_space
from tools.build_hybrid import native_compilation


def observed_flags(export_path, manifest_path, extension, correction=None):
    """Recompute the post-build observation from immutable exported bytes."""
    export = json.loads(export_path.read_text())
    directory = export_path.parent
    for name, entry in export['files'].items():
        path = directory / name
        if Path(name).name != name or sha(path) != entry['sha256'] or path.stat().st_size != entry['bytes']:
            raise ValueError('Exported compilation input changed: ' + name)
    if (sha(manifest_path) != export['files']['build-manifest.json']['sha256'] or
            sha(extension) != export['files']['swoole.so']['sha256']):
        raise ValueError('Compilation observation does not identify this artifact pair')
    observed = native_compilation(directory, directory / 'build.log')
    expected = export['native_compilation_observation']
    if correction:
        rows = [row for row in json.loads(correction.read_text())['observations'].values()
                if row['export_sha256'] == sha(export_path)]
        if len(rows) != 1:
            raise ValueError('Compiler correction does not uniquely bind this export')
        expected = rows[0]['native_compilation_observation']
    if observed != expected or not observed['compile_command_count']:
        raise ValueError('Compilation observation does not match retained commands')
    flags = observed['make_variables'].get('CXXFLAGS', '')
    extra = observed['make_variables'].get('EXTRA_CXXFLAGS', '')
    if extra:
        flags += ' ' + extra
    commands = [line for line in (directory / 'build.log').read_text().splitlines() if '--mode=compile ' in line]
    for command in commands:
        optimizations = [token for token in shlex.split(command) if token.startswith('-O')]
        if not optimizations or optimizations[-1] not in ['-O2', '-O3', '-Os', '-Oz']:
            raise ValueError('Observed compiler command is not explicitly optimized')
    return flags


def eligibility(selected, native, observed=None):
    blockers = []
    left, right = selected.get('inputs', {}), native.get('inputs', {})
    if not all(isinstance(inputs.get('fix_halfclose'), bool) for inputs in [left, right]):
        blockers.append('Native halfclose profile identities are missing')
    elif left['fix_halfclose'] != right['fix_halfclose']:
        blockers.append('Native halfclose correction differs between the artifact profiles')
    if not all(isinstance(inputs.get('compiler'), str) and inputs['compiler'] for inputs in [left, right]):
        blockers.append('Native compiler identities are missing')
    elif left['compiler'] != right['compiler']:
        blockers.append('Native compiler identities differ')
    if not left.get('upstream_commit') or left.get('upstream_commit') != right.get('upstream_commit'):
        blockers.append('Pinned native reference source identities are missing or differ')
    for name in ['php', 'php_config', 'phpize', 'effective_cppflags']:
        if (not all(isinstance(inputs.get(name), str) for inputs in [left, right]) or
                (name != 'effective_cppflags' and not left.get(name)) or left.get(name) != right.get(name)):
            blockers.append('Native PHP/configuration identity missing or different: ' + name)
    configurations = [inputs.get('effective_configure') for inputs in [left, right]]
    if not all(isinstance(value, list) and value and all(isinstance(token, str) for token in value)
               for value in configurations):
        blockers.append('Native configure profiles are missing')
    else:
        # Only backend/module selection may differ in this combined comparison.
        def native_options(tokens):
            return [token for token in tokens if token != '--without-swoole-rs' and
                    not token.startswith(('--with-swoole-rs=', '--enable-swoole-rs-'))]
        if native_options(configurations[0]) != native_options(configurations[1]):
            blockers.append('Native configure options differ outside Rust backend selection')
    flags = observed or [inputs.get('effective_cxxflags') for inputs in [left, right]]
    if not all(isinstance(value, str) and value for value in flags):
        blockers.append('Actual native C++ optimization flags are not attested in both manifests')
    else:
        if flags[0] != flags[1]:
            blockers.append('Actual native C++ flags differ')
        for value in flags:
            optimizations = [token for token in shlex.split(value) if token.startswith('-O')]
            if not optimizations or optimizations[-1] not in ['-O2', '-O3', '-Os', '-Oz']:
                blockers.append('Native C++ profile is not explicitly optimized')
                break
    profile = selected.get('rust_compilation', {}).get('artifact', {}).get('profile', {})
    if str(profile.get('opt_level')) not in ['2', '3', 's', 'z'] or profile.get('debug_assertions') is not False:
        blockers.append('Selected Rust artifact is not an attested optimized profile')
    return blockers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', action='append', required=True)
    parser.add_argument('--build-manifest', type=Path, required=True)
    parser.add_argument('--native-build-manifest', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--selected-export', type=Path)
    parser.add_argument('--native-export', type=Path)
    parser.add_argument('--compilation-correction', type=Path)
    parser.add_argument('--source-ref', required=True)
    parser.add_argument('--php', default='php')
    parser.add_argument('--php-extension', action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    work = output.parent / ('phpcollections-prepared-' + uuid.uuid4().hex)
    work.mkdir(parents=True)
    report = dict(passed=False, scope=__doc__, work=str(work),
                  measurement_performed=False, measurement_eligible=False, commands=[])
    try:
        require_build_space(ROOT)
        require_build_space(work)
        selected = json.loads(args.build_manifest.read_text())
        native = json.loads(args.native_build_manifest.read_text())
        flags = [flag for name in args.php_extension for flag in ['--php-extension', name]]
        engines = [flag for engine in args.engine for flag in ['--engine', engine]]
        runtime_path = work / 'runtime.json'
        command = [sys.executable, ROOT / 'tests/modules/phpcollections/php_runtime.py',
                   '--php', args.php, *flags, *engines, '--build-manifest', args.build_manifest,
                   '--archive', args.archive, '--source-ref', args.source_ref, '--output', runtime_path]
        result = subprocess.run(list(map(str, command)), capture_output=True, text=True)
        report['commands'].append(dict(command=list(map(str, command)), exit=result.returncode,
                                       stdout=result.stdout, stderr=result.stderr))
        if result.returncode:
            raise ValueError('Source-attested runtime prerequisite failed')
        runtime = json.loads(runtime_path.read_text())
        if not runtime['passed'] or len(runtime['engines']) != 2:
            raise ValueError('An actual native/selected runtime pair is required')
        report['runtime'] = runtime
        fixture = work / 'benchmark.php'
        fixture.write_bytes(Path(__file__).with_name('benchmark.php').read_bytes())
        for engine in runtime['engines']:
            if not engine['rust_feature_bits'] & 33554432 and engine['sha256'] != native['extension_sha256']:
                raise ValueError('Native manifest does not identify the actual control extension')
            command = Engine(engine['name'], Path(engine['extension']), args.php, tuple(args.php_extension)).command(
                '-d', 'disable_functions=hrtime,microtime', fixture, '--check')
            result = run_isolated(command, timeout=45, cwd=work)
            row = dict(engine=engine['name'], command=command, exit=result.returncode,
                       stdout=result.stdout, stderr=result.stderr)
            report['commands'].append(row)
            if result.returncode or result.stderr:
                raise ValueError('Prepared workload correctness failed; raw output retained')
            row['checks'] = json.loads(result.stdout)
            if (not row['checks']['passed'] or row['checks']['measurement_performed'] or
                    any(item['elapsed_ns'] is not None for item in row['checks']['checks'])):
                raise ValueError('Preparation unexpectedly measured time')
            if sha(engine['extension']) != engine['sha256']:
                raise ValueError('Copied extension changed during preparation')
        results = [row['checks'] for row in report['commands'] if 'checks' in row]
        if results[0] != results[1]:
            raise ValueError('Native/selected workload checksums differ')
        if (sha(args.build_manifest) != runtime['source_attestation']['manifest_sha256'] or
                sha(args.archive) != runtime['source_attestation']['archive_sha256']):
            raise ValueError('Selected manifest/archive changed during preparation')
        observed = None
        if bool(args.selected_export) != bool(args.native_export):
            raise ValueError('Both post-build export observations are required')
        if args.selected_export:
            selected_engine = next(row for row in runtime['engines'] if row['rust_feature_bits'] & 33554432)
            native_engine = next(row for row in runtime['engines'] if not row['rust_feature_bits'] & 33554432)
            observed = [observed_flags(args.selected_export, args.build_manifest, selected_engine['extension'], args.compilation_correction),
                        observed_flags(args.native_export, args.native_build_manifest, native_engine['extension'], args.compilation_correction)]
            for label, source in [('selected', args.selected_export), ('native', args.native_export)]:
                destination = work / (label + '-compilation')
                destination.mkdir()
                for name in ['export.json', *json.loads(source.read_text())['files']]:
                    shutil.copy2(source.parent / name, destination / name)
                correction = None
                if args.compilation_correction:
                    correction = destination / 'compilation-correction.json'
                    shutil.copy2(args.compilation_correction, correction)
                observed_flags(destination / 'export.json', destination / 'build-manifest.json', destination / 'swoole.so', correction)
        report['observed_cxxflags'] = observed
        report['blockers'] = eligibility(selected, native, observed)
        report['measurement_eligible'] = not report['blockers']
        for name, source in [('selected-build.json', args.build_manifest), ('native-build.json', args.native_build_manifest),
                             ('libswoole_rs_ffi.a', args.archive)]:
            shutil.copy2(source, work / name)
        report['artifacts'] = {str(path.relative_to(work)): dict(sha256=sha(path), bytes=path.stat().st_size)
                               for path in work.rglob('*') if path.is_file()}
        for path in work.rglob('*'):
            if path.is_file():
                path.chmod(0o444)
        report['passed'] = True
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
    write_report(output, report)
    print(json.dumps({key: report.get(key) for key in ['passed', 'error', 'work', 'measurement_eligible', 'blockers']}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())

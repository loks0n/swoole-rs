#!/usr/bin/env python3
"""Compile optimized actual-call comparisons; execute correctness only, never timings."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.harness import run_isolated
from tools.native_core import library_identity, verify_loader_output

EXPECTED = dict(pack_type_sizes=58, gcd=65535, lcm_wrapped=0, lcm_regular=48, decimal=111,
                radix_alloc_release=116, hex=2684326189, version_equal=2,
                version_different=1, dirname=27, mkdir_existing=1)
def clean_environment():
    env = os.environ.copy()
    removed = {key: env.pop(key) for key in list(env)
               if key.startswith(('DYLD_PRINT_', 'LD_DEBUG', 'LD_TRACE_'))
               or key in ('LD_VERBOSE', 'LD_WARN', 'LD_SHOW_AUXV', 'LD_PROFILE', 'LD_PROFILE_OUTPUT')}
    for key in ('LD_PRELOAD', 'LD_AUDIT', 'DYLD_INSERT_LIBRARIES'):
        if env.get(key):
            raise ValueError('Injected libraries require a separate matched protocol: ' + key)
    return env, removed



def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Matching configured native header tree')
    parser.add_argument('--native-build', type=Path, required=True, help='Immutable full-core build report')
    parser.add_argument('--rust-build', type=Path, required=True, help='Corebase-selected full-core build report')
    parser.add_argument('--identity', type=Path, required=True, help='Audited paired original-case receipt, or published corebase full-originals evidence')
    parser.add_argument('--include', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve(); args.output.parent.mkdir(parents=True, exist_ok=True)
    attempt = args.output.parent.resolve() / ('corebase-compare-' + uuid.uuid4().hex); attempt.mkdir()
    report = dict(created_utc=datetime.now(timezone.utc).isoformat(), passed=False,
                  scope='Optimized actual native public calls, correctness preparation only. No timing, ratio, default activation or full configuration claim.',
                  command=[], engines={}, expected_per_iteration=EXPECTED, attempt=str(attempt))
    try:
        identity = json.loads(args.identity.read_text())
        if 'platforms' in identity:
            identity = identity['platforms']['macos' if platform.system() == 'Darwin' else 'linux']
        report['identity_receipt'] = str(args.identity.resolve()); report['identity_receipt_sha256'] = sha(args.identity)
        system = platform.system(); name = 'libswoole.6.2.2.dylib' if system == 'Darwin' else 'libswoole.so.6.2.2'
        env, report['removed_tracing'] = clean_environment()
        for label, path in [('native', args.native_build.resolve()), ('rust', args.rust_build.resolve())]:
            build = json.loads(path.read_text()); modules = build['inputs']['modules']
            if bool(modules) != (label == 'rust') or (label == 'rust' and modules != ['corebase']):
                raise ValueError('Require original control and corebase-only selected callers')
            if sha(source / 'config.h') != build['inputs']['config_sha256']:
                raise ValueError('Configured header identity differs from build')
            attested = identity['engines'][label]
            original = Path(attested['library'])
            if (attested['source_receipt_sha256'] != sha(path) or not attested['selected_cases_passed']
                    or sha(original) != attested['library_before_sha256']
                    or sha(original) != attested['library_after_sha256']):
                raise ValueError('Actual library or build report differs from original-case identity receipt')
            folder = attempt / label; folder.mkdir(); library = folder / name; shutil.copy2(original, library)
            if sha(original) != sha(library): raise ValueError('Library changed during snapshot')
            report['engines'][label] = dict(build_report=str(path), build_report_sha256=sha(path),
                build_inputs=build['inputs'], source_library=str(original), library=library_identity(library))
        native = Path(report['engines']['native']['library']['path'])
        executable = attempt / 'corebase-compare'
        command = ['c++', '-std=c++14', '-O3', '-DNDEBUG', '-I' + str(source), '-I' + str(source / 'include')]
        command += ['-I' + str(p.resolve()) for p in args.include]
        command += [str(Path(__file__).with_name('benchmark.cc')), str(native), '-Wl,-rpath,' + str(native.parent), '-pthread', '-o', str(executable)]
        result = run_isolated(command, cwd=ROOT, timeout=60, env=env)
        (attempt / 'compile.log').write_text(result.stdout + result.stderr)
        report.update(command=command, compiler=subprocess.check_output(['c++', '--version'], text=True).splitlines()[0])
        if result.returncode: raise ValueError('Optimized driver compile failed')
        report['executable_sha256'] = sha(executable)
        directory = attempt / 'paths/one/two/three'
        selection = 'DYLD_LIBRARY_PATH' if system == 'Darwin' else 'LD_LIBRARY_PATH'
        for label, row in report['engines'].items():
            expected = row['library']; chosen = {**env, selection: str(Path(expected['path']).parent)}
            setting = 'DYLD_PRINT_LIBRARIES' if system == 'Darwin' else 'LD_TRACE_LOADED_OBJECTS'
            probe = run_isolated([str(executable), '--identify'], cwd=attempt, timeout=30, env={**chosen, setting: '1'})
            log = attempt / (label + '-loader.log'); log.write_text(probe.stdout + probe.stderr)
            if probe.returncode: raise ValueError('Loader identity probe failed')
            row['loader'] = verify_loader_output(probe.stdout + probe.stderr, expected, system)
            checked = run_isolated([str(executable), '--check', '1', str(directory)], cwd=attempt, timeout=30, env=chosen)
            log = attempt / (label + '-check.log'); log.write_text(checked.stdout + checked.stderr)
            if checked.returncode or checked.stderr: raise ValueError('Actual-call correctness preflight failed')
            rows = [json.loads(line) for line in checked.stdout.splitlines()]
            if len(rows) != len(EXPECTED) or any('elapsed_ns' in r or r['iterations'] != 1 for r in rows):
                raise ValueError('Unexpected check record or accidental timing')
            values = {r['workload']: r['checksum'] for r in rows}
            if values != EXPECTED: raise ValueError('Independent expected checksum mismatch: ' + repr(values))
            if library_identity(expected['path']) != expected: raise ValueError('Library changed during check')
            row.update(checksums=values, measure_command_template=[str(executable), '--measure', 'ITERATIONS', str(directory)],
                       measure_environment={selection: chosen[selection]},
                       measure_workloads={name: [str(executable), '--measure', 'ITERATIONS', str(directory), name] for name in EXPECTED},
                       calls_per_iteration={name: 14 if name == 'pack_type_sizes' else 1 for name in EXPECTED},
                       warmup='One in-process iteration per selected workload before timing; startup/setup/printing outside window', passed=True)
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
    body = json.dumps(report, indent=2) + '\n'
    (attempt / 'report.json').write_text(body)
    args.output.write_text(body)
    print(json.dumps({k: report.get(k) for k in ['passed', 'error', 'attempt']}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())

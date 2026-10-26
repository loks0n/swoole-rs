#!/usr/bin/env python3
"""Ordinary inline Channel metadata/opaque-queue proof; never Native runtime.

Existing actual-header assertions remain unchanged. Rust ASan and Native C++
sanitation are separate profiles, never an unqualified mixed-runtime link.
"""
import argparse
import hashlib
import json
from pathlib import Path
import os
import subprocess
import sys
import uuid
from ordered_gate import ROOT, PIN
sys.path.insert(0, str(ROOT))
from tools.build_hybrid import apply_patch_verified, patches_for
from tools.build_upstream import require_build_space
from tools.harness import run_isolated, write_report


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stage(source, target, manifest, patch_reader):
    for entry in manifest['patches']:
        for name in entry['upstream_paths']:
            path = target / name
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(subprocess.check_output(['git', '-C', str(source), 'show', PIN + ':' + name]))
    proofs = []
    for entry in manifest['patches']:
        patch = target / entry['path']
        patch.write_bytes(patch_reader(entry['path']))
        proofs.append(apply_patch_verified(target, patch, entry['upstream_paths'], entry['sha256']))
    return proofs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--archive', type=Path, help='Source-matched actual FFI archive, never replaced; require ABI1/M06 bit')
    args = parser.parse_args()
    output = args.report.resolve()
    if output.exists():
        parser.error('Use a unique receipt')
    work = output.parent / ('channel-state-gate-' + uuid.uuid4().hex)
    work.mkdir(parents=True)
    manifest_path = ROOT / 'migration/patches/coroutine/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    paths = [Path(__file__), Path(__file__).with_name('channel_state.c'), Path(__file__).with_name('tokens.c'),
             Path(__file__).with_name('status.c'),
             Path(__file__).with_name('context_cells.c'),
             Path(__file__).with_name('identity.c'), Path(__file__).with_name('make_coroutine_identity.py'),
             Path(__file__).with_name('swap.c'), Path(__file__).with_name('make_coroutine_swap.py'),
             Path(__file__).with_name('make_coroutine_creation.py'),
             Path(__file__).with_name('entry.c'), Path(__file__).with_name('entry.cc'), Path(__file__).with_name('entry.py'), Path(__file__).with_name('make_coroutine_entry.py'),
             Path(__file__).with_name('bailout.c'), Path(__file__).with_name('make_coroutine_bailout.py'),
             Path(__file__).with_name('creation.c'), Path(__file__).with_name('creation.cc'), Path(__file__).with_name('creation.py'),
             Path(__file__).with_name('tokens.py'), Path(__file__).with_name('tokens.cc'), manifest_path,
             *[manifest_path.parent / entry['path'] for entry in manifest['patches']],
             *sorted((ROOT / 'native/coroutine').glob('*.h')),
             *sorted((ROOT / 'crates/coroutine/src').glob('*.rs'))]
    if args.archive:
        paths.append(args.archive.resolve())
    inputs = {str(p.resolve()): sha(p) for p in paths}
    report = dict(passed=False, full_gate_passed=False, scope=__doc__, work=str(work), commands=[],
                  inputs_sha256=inputs, supplied_archive_source_attested_here=False,
                  rust_std_instrumented=False, runtime_executed=False, measurement_performed=False,
                  linux_execution='NOT_RUN while service unavailable; activation blocker')

    def run(command, env=None):
        require_build_space(work)
        result = run_isolated(list(map(str, command)), cwd=ROOT, timeout=120, **({'env': env} if env else {}))
        report['commands'].append(dict(command=list(map(str, command)), exit=result.returncode,
                                       stdout=result.stdout, stderr=result.stderr))
        write_report(output, report)
        if result.returncode:
            raise ValueError('Required ordinary control failed')
        return result

    try:
        modules = json.loads((ROOT / 'migration/modules.json').read_text())['modules']
        validated = patches_for([module for module in modules if module['id'] == 'M06'])
        report['canonical_patch_destination_preflight_count'] = len(validated)
        current = work / 'current'
        report['patch_proofs'] = stage(args.source, current, manifest, lambda name: (manifest_path.parent / name).read_bytes())
        archive = args.archive.resolve() if args.archive else work / 'libcoroutine.a'
        if not args.archive:
            run(['rustc', '--edition=2024', '--crate-type=staticlib', '-C', 'opt-level=2', '-D', 'warnings', ROOT / 'crates/coroutine/src/lib.rs', '-o', archive])
        report['archive_mode'] = 'supplied_actual_FFI_ABI1_M06_bit' if args.archive else 'private_module_only_opt2'
        for sanitize in [False, True]:
            binary = work / ('rust-' + str(sanitize))
            obj = binary.with_suffix('.o')
            run(['rustc', '--edition=2024', '--test', '-C', 'opt-level=2', '-D', 'warnings', ROOT / 'crates/coroutine/src/lib.rs', '--emit=obj=' + str(obj) + ',link=' + str(binary), *(['-Zsanitizer=address'] if sanitize else [])], {**os.environ, 'RUSTC_BOOTSTRAP': '1'} if sanitize else None)
            run([binary])
            if sanitize:
                symbols = run(['nm', '-u', obj]).stdout
                report['positive_rust_asan_report_imports'] = sorted({line.strip() for line in symbols.splitlines() if '__asan_report_' in line})
                if not report['positive_rust_asan_report_imports']:
                    raise ValueError('Owned Rust instructions not instrumented')
            receipt = work / ('actual-header-' + str(sanitize) + '.json')
            run(['python3', Path(__file__).with_name('tokens.py'), '--source', args.source, '--archive', archive, '--report', receipt, *(['--sanitize'] if sanitize else [])])
            report.setdefault('actual_header_reports', []).append(dict(path=str(receipt), result=json.loads(receipt.read_text())))
        for fixture in ['tokens.c', 'channel_state.c', 'status.c', 'context_cells.c', 'identity.c', 'creation.c', 'entry.c']:
            obj = work / (fixture + '.o')
            binary = work / (fixture + '-abi')
            command = ['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-UNDEBUG',
                       '-I' + str(ROOT / 'native/coroutine'), '-I' + str(ROOT / 'native/include'),
                       '-c', Path(__file__).with_name(fixture), '-o', obj]
            if args.archive and fixture in ['channel_state.c', 'status.c', 'context_cells.c', 'identity.c', 'creation.c']:
                command.append('-DSWR_CHANNEL_FFI')
            run(command)
            run(['c++', obj, archive, '-lpthread', *(['-ldl', '-lm'] if sys.platform.startswith('linux') else []), '-o', binary])
            run([binary])
        # Typed function identities/descriptors only; no callback is invoked.
        report['swap_abi_profiles'] = []
        for fixture in ['swap', 'bailout']:
          for standard in ['c11', 'c++14', 'c++17']:
            for sanitized in [False, True]:
                binary = work / (fixture + '-' + standard + '-' + str(sanitized))
                obj = binary.with_suffix('.o')
                sanitizer = ['-fsanitize=address,undefined', '-fno-sanitize-recover=all'] if sanitized else []
                run(['cc' if standard == 'c11' else 'c++', '-x', 'c' if standard == 'c11' else 'c++',
                     '-std=' + standard, '-O2', '-Wall', '-Wextra', '-Werror', '-UNDEBUG',
                     '-I' + str(ROOT / 'native/coroutine'), *sanitizer, '-c', Path(__file__).with_name(fixture + '.c'), '-o', obj])
                run(['c++', obj, archive, '-lpthread', *(['-ldl', '-lm'] if sys.platform.startswith('linux') else []), *sanitizer, '-o', binary])
                run([binary])
                report['swap_abi_profiles'].append(dict(fixture=fixture, standard=standard, native_sanitized=sanitized,
                    rust_instrumented=False, callback_invoked=False))
        creation_receipt = work / 'creation-exact-bodies.json'
        run(['python3', Path(__file__).with_name('creation.py'), '--source', args.source,
             '--archive', archive, '--report', creation_receipt])
        report['creation_exact_bodies'] = dict(path=str(creation_receipt),
                                              result=json.loads(creation_receipt.read_text()))
        entry_receipt = work / 'entry-exact-bodies.json'
        run(['python3', Path(__file__).with_name('entry.py'), '--source', args.source,
             '--archive', archive, '--report', entry_receipt])
        report['entry_exact_bodies'] = dict(path=str(entry_receipt), result=json.loads(entry_receipt.read_text()))
        if any(sha(path) != digest for path, digest in inputs.items()):
            raise ValueError('Owned or supplied archive input changed')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
    write_report(output, report)
    print(json.dumps({key: report.get(key) for key in ['passed', 'error', 'work']}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())

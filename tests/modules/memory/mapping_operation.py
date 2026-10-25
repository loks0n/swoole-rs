#!/usr/bin/env python3
"""SharedMemory source TUs and actual selected bodies with inert success effects; no OS mapping/runtime parity."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.build_hybrid import apply_patch_verified
from tools.harness import run_isolated

PIN = '8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e'
SOURCE = 'src/memory/shared_memory.cc'
GUARD = 4 * 1024**3


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def selected_model(text):
    """Keep complete actual selected class/methods and all five global wrappers."""
    start = text.index('struct SharedMemory {')
    middle = text.index('}  // namespace swoole', start)
    wrappers = text.index('void *sw_shm_malloc(', middle)
    return ('#include "mapping_operation_model.h"\n#include <cerrno>\nnamespace model {\n'
            + text[start:middle] + text[wrappers:] + '\n}\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--cxx', default='c++')
    parser.add_argument('--cc', default='cc')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Refusing to overwrite an existing receipt')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {'passed': False, 'scope': __doc__, 'commands': [], 'upstream_commit': PIN,
              'guard_bytes': GUARD, 'rust_archive_instrumented': False,
              'archive_source_correspondence': 'Caller must supply source-qualified immutable archive; not inferred from ABI/export presence',
              'unqualified': ['actual OS/File/resource effects', 'error/errno/warning/failure paths',
                              'IPC/fork/thread/lifetime', 'Linux', 'production', 'original runtime parity',
                              'performance', 'default activation'],
              'forced_file_support_adapter': 'Original forced fallback requires explicit pinned swoole_file.h; original missing-header failure retained separately',
              'syntax_warning_policy': 'Strict -Werror except pinned upstream unused parameters explicitly suppressed'}
    owned = [Path(__file__), *sorted(Path(__file__).parent.glob('mapping_operation*')),
             *sorted((ROOT / 'crates/memory/src').rglob('*.rs')), ROOT / 'native/memory/swoole_rs_memory.h']
    report['source_sha256'] = {str(p.relative_to(ROOT)): sha(p) for p in owned if p.is_file()}
    try:
        archive = args.archive.resolve(strict=True)
        report['archive'] = str(archive)
        report['archive_sha256'] = sha(archive)
        report['compiler'] = {'cxx': subprocess.check_output([*shlex.split(args.cxx), '--version'], text=True),
                              'cc': subprocess.check_output([*shlex.split(args.cc), '--version'], text=True)}
        manifest = json.loads((ROOT / 'migration/patches/memory/manifest.json').read_text())
        assert manifest['upstream_commit'] == PIN
        entry = next(p for p in manifest['patches'] if SOURCE in p['upstream_paths'])
        report['patch'] = entry
        bundle = subprocess.check_output(['git', '-C', str(args.source), 'archive', PIN, 'include', SOURCE], timeout=20)
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', 'openssl'], text=True))
        with tempfile.TemporaryDirectory(prefix='swr-mapping-operation-') as temporary:
            tree = Path(temporary)
            for variant in ['original', 'selected']:
                with tarfile.open(fileobj=io.BytesIO(bundle)) as tar:
                    for member in tar:
                        if member.isfile():
                            path = tree / variant / member.name
                            path.parent.mkdir(parents=True, exist_ok=True)
                            path.write_bytes(tar.extractfile(member).read())
            report['patch_application'] = apply_patch_verified(tree / 'selected', ROOT / 'migration/patches/memory' / entry['path'], entry['upstream_paths'], entry['sha256'])
            def run(label, argv, compile=False):
                if compile:
                    free = {str(p): shutil.disk_usage(p).free for p in [ROOT, tree, args.output.parent]}
                    if min(free.values()) < GUARD:
                        report['commands'].append({'case': label, 'argv': argv, 'blocked': 'unchanged 4GiB guard', 'free_bytes': free})
                        raise RuntimeError('Compiler refused by unchanged 4GiB guard')
                result = run_isolated(argv, cwd=ROOT, timeout=60)
                report['commands'].append({'case': label, 'argv': argv, 'returncode': result.returncode,
                                           'stdout': result.stdout, 'stderr': result.stderr})
                if result.returncode:
                    raise RuntimeError(f'{label} failed with exit {result.returncode}')
                return result
            includes = ['-I' + str(ROOT / 'native/memory'), '-I' + str(ROOT / 'native/include')]
            for variant in ['original', 'selected']:
                for backend in ['anonymous', 'file', 'no-map-failed']:
                    wrapper = tree / (variant + '-' + backend + '.cc')
                    prefix = '#include <sys/mman.h>\n'
                    if backend == 'file':
                        prefix += '#undef MAP_ANONYMOUS\n#undef MAP_ANON\n#include \"swoole_file.h\"\n'
                    if backend == 'no-map-failed':
                        prefix += '#undef MAP_FAILED\n'
                    wrapper.write_text(prefix + '#include ' + json.dumps(str(tree / variant / SOURCE)) + '\n')
                    for standard in ['c++14', 'c++17']:
                        run(f'{variant}-{backend}-{standard}', [*shlex.split(args.cxx), '-std=' + standard,
                            '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-fsyntax-only',
                            *(['-DSWOOLE_RS_MEMORY=1'] if variant == 'selected' else []),
                            '-I' + str(tree / variant / 'include'), *includes, *flags, str(wrapper)], compile=True)
            model = tree / 'selected-model.cc'
            model.write_text(selected_model((tree / 'selected' / SOURCE).read_text()))
            sanitize = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
            fixture = Path(__file__).parent
            for backend in ['anonymous', 'file']:
                binary = tree / ('success-' + backend)
                run('compile-success-' + backend, [*shlex.split(args.cxx), '-std=c++14', '-O1', '-g',
                    '-Wall', '-Wextra', '-Werror', *sanitize,
                    *(['-DSWR_MODEL_FILE_BACKEND=1'] if backend == 'file' else []),
                    '-I' + str(fixture), *includes, str(model), str(fixture / 'mapping_operation_model.cc'),
                    str(archive), '-lpthread', '-ldl', '-lm', '-o', str(binary)], compile=True)
                value = json.loads(run('success-' + backend, [str(binary)]).stdout)
                assert value['passed'] and value['actual_native_success_cases'] == 16 and value['explicit_os_calls'] == 0
                report.setdefault('results', {})[backend] = value
            obj, binary = tree / 'ffi.o', tree / 'ffi'
            run('compile-c11', [*shlex.split(args.cc), '-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                *sanitize, *includes, '-c', str(fixture / 'mapping_operation.c'), '-o', str(obj)], compile=True)
            run('link-c11', [*shlex.split(args.cxx), *sanitize, str(obj), str(archive), '-lpthread', '-ldl', '-lm', '-o', str(binary)], compile=True)
            value = json.loads(run('actual-c11', [str(binary)]).stdout)
            assert value['passed'] and value['explicit_os_calls'] == 0
            report['results']['c11'] = value
            assert sha(archive) == report['archive_sha256']
            assert report['source_sha256'] == {p: sha(ROOT / p) for p in report['source_sha256']}
            report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report.get(k) for k in ['passed', 'error', 'results']}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""Prepare optimized immutable ordinary registry workloads; no clock reads/timings.

The exported archive is copied, verified and linked unchanged. Actual pinned and
selected get/count/GDB source bodies are extracted without replacing algorithms.
This prepares future measurements, not runtime/activation or performance proof.
"""
import argparse
import hashlib
import json
import shlex
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.build_hybrid import apply_patch_verified
from tools.build_upstream import require_build_space


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True, help='Read-only pinned upstream Git repository')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report = args.report.resolve()
    if report.exists():
        parser.error('Use a unique receipt')
    work = report.parent / ('registry-prepared-' + uuid.uuid4().hex)
    work.mkdir(parents=True)
    receipt = dict(passed=False, measurement_performed=False, clock_reads_in_check=False,
                   runtime_executed=False, linux_qualified=False, activation=False,
                   scope=__doc__, work=str(work), commands=[], results=[])

    def run(command, cwd=work):
        # No timeout, timestamp or elapsed-time wrapper in preparation.
        require_build_space(work)
        result = subprocess.run(list(map(str, command)), cwd=cwd, capture_output=True, text=True)
        receipt['commands'].append(dict(command=list(map(str, command)), exit=result.returncode,
                                        stdout=result.stdout, stderr=result.stderr))
        report.write_text(json.dumps(receipt, indent=2) + '\n')
        if result.returncode or result.stderr:
            raise ValueError('Command failed or warned; see retained receipt')
        return result.stdout

    def frozen(path):
        return subprocess.check_output(['git', '-C', str(ROOT), 'show', ref + ':' + path])

    try:
        export = args.export.resolve()
        identity = json.loads((export / 'export.json').read_text())
        ref = identity['source_ref']
        receipt['source_ref'] = ref
        inputs = {str(export / 'export.json'): sha(export / 'export.json')}
        for name, row in identity['files'].items():
            if sha(export / name) != row['sha256']:
                raise ValueError('Export identity mismatch: ' + name)
            inputs[str(export / name)] = row['sha256']
        fixture = Path(__file__).with_suffix('.cc').with_name('registry_benchmark.cc')
        for path in [Path(__file__), fixture]:
            inputs[str(path)] = sha(path)
        receipt['inputs_sha256'] = inputs
        production = json.loads((export / 'build-manifest.json').read_text())
        compilation = production.get('rust_compilation', {})
        profile = compilation.get('artifact', {}).get('profile', {})
        if profile.get('opt_level') not in ['2', '3'] or profile.get('debug_assertions', True):
            raise ValueError('Actual optimized non-debug Rust artifact profile required')
        receipt['rust_compilation'] = compilation
        archive = work / 'libswoole_rs_ffi.a'
        shutil.copyfile(export / archive.name, archive)
        manifest_path = 'migration/patches/coroutine/manifest.json'
        manifest = json.loads(frozen(manifest_path))
        pin = manifest['upstream_commit']
        receipt['pin'] = pin
        tree = work / 'source'
        originals = {}
        for patch in manifest['patches']:
            for name in patch['upstream_paths']:
                if name not in originals:
                    originals[name] = subprocess.check_output(['git', '-C', str(args.source), 'show', pin + ':' + name])
                    dest = tree / name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(originals[name])
            patchfile = work / patch['path']
            patchfile.write_bytes(frozen('migration/patches/coroutine/' + patch['path']))
            apply_patch_verified(tree, patchfile, patch['upstream_paths'], patch['sha256'])
        headers = work / 'headers'
        headers.mkdir()
        for name in ['swoole_rs_coroutine.h', 'swoole_rs_coroutine_registry.h']:
            (headers / name).write_bytes(frozen('native/coroutine/' + name))
        receipt['compiler_identity'] = run(['c++', '--version'])
        dependencies = run(['c++', '-std=c++14', '-M', '-x', 'c++', '-include', 'unordered_map', '/dev/null'])
        paths = [Path(x) for x in shlex.split(dependencies.replace('\\\n', ' '))[1:] if Path(x).is_file()]
        receipt['stdlib_headers_sha256'] = {str(p): sha(p) for p in paths}
        for engine in ['native', 'selected']:
            folder = work / engine
            folder.mkdir()
            body = originals['src/coroutine/base.cc'] if engine == 'native' else (tree / 'src/coroutine/base.cc').read_bytes()
            marker = b'swoole::Coroutine *swoole_coroutine_get('
            (folder / 'registry-callers.inc').write_bytes(body[body.index(marker):])
            shutil.copyfile(fixture, folder / 'registry_benchmark.cc')
            binary = folder / 'registry-benchmark'
            command = ['c++', '-std=c++14', '-O2', '-g', '-Wall', '-Wextra', '-Werror', '-UNDEBUG',
                       '-I' + str(headers), '-I' + str(folder), str(folder / 'registry_benchmark.cc')]
            if engine == 'selected':
                command += ['-DSWOOLE_RS_COROUTINE_REGISTRY_V2=1', str(archive), '-lpthread', '-lm']
                if sys.platform == 'linux':
                    command += ['-ldl']
            run(command + ['-o', binary])
            output = run([binary, '--check'])
            rows = [json.loads(line) for line in output.splitlines()]
            if len(rows) != 6:
                raise ValueError('Incomplete workload output')
            receipt['results'].append(dict(engine=engine, checks=rows, binary=str(binary)))
        if receipt['results'][0]['checks'] != receipt['results'][1]['checks']:
            raise ValueError('Native/selected preparation mismatch; measurement remains blocked')
        if any(sha(path) != value for path, value in inputs.items()):
            raise ValueError('Borrowed or owned input changed')
        if any(sha(path) != value for path, value in receipt['stdlib_headers_sha256'].items()):
            raise ValueError('Compiler headers changed')
        receipt['artifacts_sha256'] = {str(p.relative_to(work)): sha(p) for p in work.rglob('*') if p.is_file()}
        # Freeze captured inputs and binaries; later consumers must recheck hashes.
        for artifact in work.rglob('*'):
            if artifact.is_file():
                artifact.chmod(artifact.stat().st_mode & ~0o222)
        receipt['passed'] = True
    except Exception as error:
        receipt['error'] = str(error)
    report.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({key: receipt.get(key) for key in ['passed', 'error', 'work', 'measurement_performed']}))
    return int(not receipt['passed'])


if __name__ == '__main__':
    sys.exit(main())

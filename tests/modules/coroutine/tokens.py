#!/usr/bin/env python3
"""Compare actual Channel header storage on ordinary opaque tokens only.

No Coroutine creation/resume/cancellation, timer, callback, retirement, failure
injection or PHP lifetime execution. Logging is an explicit inert native facade.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.build_hybrid import apply_patch_verified
from tools.build_upstream import require_build_space
from tools.harness import run_isolated, write_report

from tools.build_upstream import COMMIT as PIN


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    args.report = args.report.resolve()
    if args.report.exists():
        parser.error('Receipt exists; choose a unique attempt path')
    args.report.parent.mkdir(parents=True, exist_ok=True)
    work = args.report.parent / ('channel-tokens-' + uuid.uuid4().hex)
    work.mkdir()
    archive = args.archive.resolve(strict=True)
    fixture = Path(__file__).with_suffix('.cc')
    sources = [fixture, Path(__file__), ROOT / 'native/coroutine/swoole_rs_coroutine.h',
               ROOT / 'native/coroutine/swoole_rs_channel_tokens.h',
               *sorted((ROOT / 'crates/coroutine/src').glob('*.rs'))]
    bound = {str(path): sha(path) for path in [archive, *sources]}
    report = dict(passed=False, full_gate_passed=False, pin=PIN, scope=__doc__,
                  work=str(work), inputs_sha256=bound, commands=[], results=[],
                  native_sanitized=args.sanitize, rust_instrumented=False,
                  supplied_archive_source_attested_here=False,
                  limits=['Supplied archive identity is recorded; caller must bind it to compiled Rust source.',
                          'Selected protected container types/class layout differ; selected SDK must rebuild.',
                          'Allocation/copy-assignment failure topology, actual waiters/PHP/lifetime and performance unqualified.'])

    def run(command):
        require_build_space(work)
        result = run_isolated(list(map(str, command)), cwd=work, timeout=90)
        report['commands'].append(dict(command=list(map(str, command)), exit=result.returncode,
                                       stdout=result.stdout, stderr=result.stderr))
        write_report(args.report, report)
        if result.returncode:
            raise ValueError('Command failed; first output retained')
        return result

    try:
        original = work / 'original'
        selected = work / 'selected'
        packed = subprocess.check_output(['git', '-C', str(args.source), 'archive', PIN,
                                         'include', 'src/coroutine/base.cc', 'src/coroutine/channel.cc', 'src/coroutine/context.cc', 'src/coroutine/thread_context.cc'])
        for tree in [original, selected]:
            tree.mkdir()
            with tarfile.open(fileobj=io.BytesIO(packed)) as contents:
                for member in contents:
                    path = Path(member.name)
                    if path.is_absolute() or '..' in path.parts:
                        raise ValueError('Unsafe reference path')
                    if member.isfile():
                        out = tree / path
                        out.parent.mkdir(parents=True, exist_ok=True)
                        out.write_bytes(contents.extractfile(member).read())
        manifest = ROOT / 'migration/patches/coroutine/manifest.json'
        report['patch_proofs'] = [apply_patch_verified(selected, manifest.parent / entry['path'],
                                  entry['upstream_paths'], entry['sha256'])
                                  for entry in json.loads(manifest.read_text())['patches']]
        includes = shlex.split(subprocess.check_output(['pkg-config', '--cflags', 'openssl'], text=True))
        libs = ['-lpthread', *(['-ldl', '-lm', '-lrt', '-lutil'] if sys.platform.startswith('linux') else [])]
        for label, tree in [('original', original), ('selected', selected)]:
            binary = work / (label + '-storage')
            command = ['c++', '-std=c++14', '-O1', '-g', '-UNDEBUG', '-I' + str(tree / 'include'),
                       '-I' + str(tree), '-I' + str(ROOT / 'native/coroutine'), *includes,
                       '-DHAVE_EPOLL' if sys.platform.startswith('linux') else '-DHAVE_KQUEUE']
            if label == 'selected':
                command += ['-DSWOOLE_RS_COROUTINE']
            command += [str(fixture), *([str(archive)] if label == 'selected' else []), *libs, '-o', str(binary)]
            if args.sanitize:
                command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
            run(command)
            result = run([str(binary)])
            if result.stderr:
                raise ValueError('Storage control warned; first output retained')
            report['results'].append(dict(engine=label, summary=json.loads(result.stdout)))
        if report['results'][0]['summary'] != report['results'][1]['summary']:
            raise ValueError('Native and Rust queue behavior differs')
        if any(sha(path) != digest for path, digest in bound.items()):
            raise ValueError('Input changed during execution')
        report.update(passed=True, inputs_before_after_equal=True)
    except Exception as error:
        report['error'] = str(error)
    write_report(args.report, report)
    print(json.dumps({key: report.get(key) for key in ['passed', 'error', 'work']}))
    return int(not report['passed'])


if __name__ == '__main__':
    sys.exit(main())

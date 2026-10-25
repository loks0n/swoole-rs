#!/usr/bin/env python3
"""Compare actual pinned/selected native bodies with ordered callback facades.

This supplements real-context/original/PHP gates. Context swaps and timers here
are deterministic native facades, not evidence of a working execution backend.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
import sys
sys.path.insert(0, str(ROOT))
from tools.build_hybrid import apply_patch_verified
from tools.build_upstream import COMMIT as PIN


def block(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    paths = ['src/coroutine/base.cc', 'src/coroutine/channel.cc']
    originals = {path: subprocess.check_output(['git', '-C', str(args.source), 'show', PIN + ':' + path], text=True) for path in paths}
    signatures = {
        paths[0]: ['void Coroutine::check_end()', 'long Coroutine::run()', 'void Coroutine::yield()',
                   'void Coroutine::yield(CancelFunc *', 'bool Coroutine::yield_ex(', 'void Coroutine::resume()',
                   'bool Coroutine::cancel()', 'void Coroutine::close()'],
        paths[1]: ['void Channel::timer_callback(', 'void Channel::yield(', 'void *Channel::pop(',
                   'bool Channel::push(', 'bool Channel::close()'],
    }
    with tempfile.TemporaryDirectory(prefix='swr-coroutine-order-') as temporary:
        tree = Path(temporary)
        staged = {**originals, 'include/swoole_coroutine_channel.h': subprocess.check_output(
            ['git', '-C', str(args.source), 'show', PIN + ':include/swoole_coroutine_channel.h'], text=True)}
        manifest = json.loads((ROOT / 'migration/patches/coroutine/manifest.json').read_text())
        for entry in manifest['patches']:
            for path in entry['upstream_paths']:
                if path not in staged:
                    staged[path] = subprocess.check_output(
                        ['git', '-C', str(args.source), 'show', PIN + ':' + path], text=True)
        for path, text in staged.items():
            output = tree / path
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(text)
        for entry in manifest['patches']:
            patch = ROOT / 'migration/patches/coroutine' / entry['path']
            if hashlib.sha256(patch.read_bytes()).hexdigest() != entry['sha256']:
                raise ValueError('Patch checksum differs')
            apply_patch_verified(tree, patch, entry['upstream_paths'], entry['sha256'])
        for variant in ['original', 'selected']:
            bodies = []
            for path in paths:
                text = originals[path] if variant == 'original' else (tree / path).read_text()
                bodies += [block(text, signature) for signature in signatures[path]]
            (tree / (variant + '.inc')).write_text('\n'.join(bodies))
        exe = tree / 'ordered'
        command = ['c++', '-std=c++14', '-O1', '-g', '-I' + str(tree), '-I' + str(ROOT / 'native/coroutine'),
                   str(ROOT / 'tests/modules/coroutine/ordered_gate.cc'), str(args.archive.resolve()), '-o', str(exe), '-lpthread']
        if args.sanitize:
            command += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        if __import__('sys').platform.startswith('linux'):
            command += ['-ldl', '-lm']
        build = subprocess.run(command, capture_output=True, text=True)
        run = subprocess.run([str(exe)], capture_output=True, text=True) if build.returncode == 0 else build
        print(build.stderr, end='')
        print(run.stdout, end='')
        if run is not build:
            print(run.stderr, end='')
        result = dict(pin=PIN, scope=__doc__, patch_manifest=manifest,
                      command=command, compile_returncode=build.returncode, compile_stderr=build.stderr,
                      returncode=run.returncode, stdout=run.stdout, stderr=run.stderr)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + '\n')
        raise SystemExit(run.returncode)


if __name__ == '__main__':
    main()

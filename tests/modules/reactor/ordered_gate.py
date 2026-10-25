#!/usr/bin/env python3
"""Compare actual pinned/patched dispatch statements with native callback facades.

This is an ordered dispatch/interest test, not a complete reactor/core test.
The reference checkout is read-only; all overlays/builds live outside Git trees.
"""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import sys

PIN = '8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e'
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.build_hybrid import apply_patch_verified


def block(source, start):
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end], end


def dispatch(source, candidate, backend):
    marker = 'for (int i = 0; i < event_num; i++)' if backend == 'poll' else 'for (int i = 0; i < n; i++)'
    return block(source, source.index(marker))[0]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--sanitize', action='store_true', help='instrument native facades with ASan/UBSan; Rust archive is separately built')
    a = p.parse_args()
    patch = ROOT / 'migration/patches/reactor/0001-readiness-policy.patch'
    sources = {name: subprocess.check_output(['git', '-C', str(a.source), 'show', f'{PIN}:{name}'], text=True)
               for name in ['src/reactor/poll.cc', 'src/reactor/epoll.cc', 'src/reactor/kqueue.cc', 'include/swoole_reactor.h']}
    with tempfile.TemporaryDirectory(prefix='swr-reactor-order-') as tmp:
        tree = Path(tmp)
        for name, text in sources.items():
            out = tree / name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text)
        # Patch includes kqueue; supply it unchanged too rather than filtering hunks.
        kqueue = tree / 'src/reactor/kqueue.cc'
        kqueue.write_bytes(subprocess.check_output(['git', '-C', str(a.source), 'show', f'{PIN}:src/reactor/kqueue.cc']))
        entry = json.loads((patch.parent/'manifest.json').read_text())['patches'][0]
        application = apply_patch_verified(tree, patch, entry['upstream_paths'], entry['sha256'])
        includes = []
        for candidate in [False, True]:
            for backend in ['poll', 'epoll']:
                name = 'src/reactor/' + backend + '.cc'
                text = (tree / name).read_text() if candidate else sources[name]
                body = dispatch(text, candidate, backend)
                raw = 'revents' if backend == 'poll' else 'events'
                includes.append(f'void Runner::run_{backend}_{int(candidate)}() {{ int event_num=batch, n=batch;\n{body}\n }}')
            ksource = (tree / 'src/reactor/kqueue.cc').read_text() if candidate else sources['src/reactor/kqueue.cc']
            body, _ = block(ksource, ksource.index('if (fetch_event(&event, udata))'))
            includes.append(f'void Runner::run_kqueue_{int(candidate)}() {{ auto *kevent=&kevents_[0]; void *udata=kevent->udata;\n{body}\n }}')
            header = (tree / 'include/swoole_reactor.h').read_text() if candidate else sources['include/swoole_reactor.h']
            methods = []
            for name in ['add_event', 'del_event', 'remove_read_event', 'remove_write_event', 'add_read_event', 'add_write_event']:
                body, _ = block(header, header.index('int ' + name + '('))
                methods.append(body.replace('network::Socket', 'Socket').replace('EventType', 'int'))
            includes.append('struct Interest' + str(int(candidate)) + ': InterestBase {\n' + '\n'.join(methods) + '\n};')
        for signature in ['bool fetch_event(', 'void del_once_socket(']:
            body, _ = block(sources['src/reactor/kqueue.cc'], sources['src/reactor/kqueue.cc'].index(signature))
            body = body.replace(signature, signature.split()[0] + ' Runner::' + signature.split()[1])
            includes.append(body)
        (tree / 'actual.inc').write_text('\n'.join(includes))
        source = ROOT / 'tests/modules/reactor/ordered_gate.cc'
        exe = tree / 'ordered'
        cmd = ['c++', '-std=c++14', '-O2', '-g', '-I' + str(tree), '-I' + str(ROOT / 'native/reactor'), str(source), str(a.archive.resolve()), '-o', str(exe), '-lpthread']
        if a.sanitize:
            cmd += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        if __import__('sys').platform.startswith('linux'):
            cmd += ['-ldl', '-lm']
        subprocess.run(cmd, check=True)
        r = subprocess.run([str(exe)], capture_output=True, text=True)
        print(r.stdout, end='')
        print(r.stderr, end='')
        result = dict(patch_application=[application], pin=PIN,
                      scope='actual extracted poll/epoll loops + kqueue socket branch + actual six inline methods; native callback/syscall facades; real poll socketpair witness',
                      compiler=subprocess.check_output(['c++', '--version'], text=True).splitlines()[0], command=cmd, returncode=r.returncode, stdout=r.stdout, stderr=r.stderr)
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(json.dumps(result, indent=2) + '\n')
        raise SystemExit(r.returncode)


if __name__ == '__main__':
    main()

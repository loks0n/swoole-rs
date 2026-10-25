#!/usr/bin/env python3
"""Compile unchanged and selected full coroutine translation units as C++14."""
from pathlib import Path
import argparse
import io
import hashlib
import json
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.build_hybrid import apply_patch_verified
from tools.build_upstream import require_build_space
from tools.build_upstream import COMMIT as PIN
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=Path, required=True)
p.add_argument('--report', type=Path, required=True)
p.add_argument('--stack-usage', action='store_true', help='Compile actual optional stack-marker callers')
p.add_argument('--timing', action='store_true', help='Compile actual optional Coroutine timing callers')
p.add_argument('--registry', action='store_true', help='Compile actual optional authoritative Rust registry callers')
p.add_argument('--standard', choices=['c++14','c++17'], default='c++14')
p.add_argument('--backend', choices=['header-default', 'asm', 'ucontext', 'thread'], default='header-default',
               help='Compile the requested Native backend; no switching or runtime execution')
a = p.parse_args()
rows = []
compiler = None
def save():
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(dict(pin=PIN, compiler=compiler, backend=a.backend, standard=a.standard, full_gate_passed=False, rows=rows), indent=2)+'\n')
with tempfile.TemporaryDirectory(prefix='swr-coroutine-compile-') as tmp:
    tree = Path(tmp)
    data = subprocess.check_output(['git', '-C', str(a.source), 'archive', PIN, 'include', 'src/coroutine/base.cc', 'src/coroutine/channel.cc', 'src/coroutine/context.cc', 'src/coroutine/thread_context.cc', 'thirdparty/multipart_parser.h'])
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for member in archive:
            if member.isfile():
                out = tree / member.name
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(archive.extractfile(member).read())
    flags = ['-std='+a.standard, '-O1', '-g', '-DSWOOLE_RS_COROUTINE', '-I'+str(tree/'include'), '-I'+str(tree), '-I'+str(ROOT/'native/coroutine'), *subprocess.check_output(['pkg-config', '--cflags', 'openssl'], text=True).split()]
    if a.backend == 'asm':
        flags += ['-DSW_USE_ASM_CONTEXT']
    elif a.backend == 'thread':
        flags += ['-DSW_USE_THREAD_CONTEXT']
    if a.registry:
        flags += ['-DSWOOLE_RS_COROUTINE_REGISTRY_V2']
    if a.stack_usage:
        flags += ['-DSW_CONTEXT_DETECT_STACK_USAGE']
    if a.timing:
        flags += ['-DSW_CORO_TIME']
    linux = sys.platform.startswith('linux')
    backends = ['base', 'channel', 'context', 'thread_context']
    flags += ['-DHAVE_EPOLL'] if linux else ['-DHAVE_KQUEUE']
    for variant in ['original', 'patched', 'disabled']:
        if variant == 'patched':
            manifest = json.loads((ROOT/'migration/patches/coroutine/manifest.json').read_text())
            for entry in manifest['patches']:
                patch = ROOT/'migration/patches/coroutine'/entry['path']
                if hashlib.sha256(patch.read_bytes()).hexdigest() != entry['sha256']:
                    raise ValueError('Patch checksum differs')
                apply_patch_verified(tree, patch, entry['upstream_paths'], entry['sha256'])
        for name in backends:
            selected_flags = [flag for flag in flags if variant != 'disabled' or flag not in ['-DSWOOLE_RS_COROUTINE', '-DSWOOLE_RS_COROUTINE_REGISTRY_V2']]
            cmd = ['c++', *selected_flags, '-c', str(tree/('src/coroutine/'+name+'.cc')), '-o', str(tree/(variant+'-'+name+'.o'))]
            try:
                require_build_space(tree)
            except RuntimeError as error:
                rows.append(dict(variant=variant, backend=name, command=cmd,
                                 returncode=None, passed=False, blocked=True,
                                 compiler_started=False, error=str(error)))
                save()
                raise SystemExit(1)
            if compiler is None:
                compiler = subprocess.check_output(['c++', '--version'], text=True).splitlines()[0]
            result = subprocess.run(cmd, capture_output=True, text=True)
            passed = result.returncode == 0 if variant != 'disabled' or name in ['context', 'thread_context'] else (result.returncode != 0 and 'Coroutine overlay requires --enable-swoole-rs-coroutine' in result.stderr)
            print(variant, name, result.returncode, 'PASS' if passed else 'FAIL', flush=True)
            rows.append(dict(variant=variant, backend=name, command=cmd, returncode=result.returncode, passed=passed, compiler_started=True, stderr=result.stderr))
            save()
save()
raise SystemExit(any(not row['passed'] for row in rows))

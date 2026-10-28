#!/usr/bin/env python3
"""Compile unchanged and selected full backend translation units as C++14."""
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
sys.path.insert(0,str(ROOT))
from tools.build_hybrid import apply_patch_verified
from tools.build_upstream import COMMIT as PIN
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=Path, required=True)
p.add_argument('--report', type=Path, required=True)
a = p.parse_args()
if a.report.exists():
    raise SystemExit('Refusing to replace an existing compile receipt')
manifest = json.loads((ROOT/'migration/patches/reactor/manifest.json').read_text())
# The hybrid always carries the graduated buffer module, whose Buffer the write path uses;
# its string storage (0003) is outside these units, as in buffer_typed_compile.py.
buffer_manifest = json.loads((ROOT/'migration/patches/buffer/manifest.json').read_text())
buffer_patches = [entry for entry in buffer_manifest['patches'] if entry['path'] != '0003-string-storage.patch']
# Stage every declared overlay destination, including narrow Admin consumers.
# Compiling the backend subset does not permit silently omitting a patch input.
inputs = sorted({'include', 'src/reactor', 'src/network/stream.cc',
                 'src/network/socket.cc', 'thirdparty/multipart_parser.h'} |
                {name for entry in manifest['patches'] + buffer_patches for name in entry['upstream_paths']})
rows = []
patch_proofs = []
with tempfile.TemporaryDirectory(prefix='swr-reactor-compile-') as tmp:
    tree = Path(tmp)
    data = subprocess.check_output(['git', '-C', str(a.source), 'archive', PIN, *inputs])
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for member in archive:
            if member.isfile():
                out = tree / member.name
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(archive.extractfile(member).read())
    flags = ['-std=c++14', '-O1', '-g', '-DSWOOLE_RS_REACTOR', '-I'+str(tree/'include'), '-I'+str(tree), '-I'+str(ROOT/'native/reactor'), *subprocess.check_output(['pkg-config', '--cflags', 'openssl'], text=True).split()]
    linux = sys.platform.startswith('linux')
    backends = ['base', 'poll', 'epoll'] if linux else ['base', 'poll', 'kqueue']
    flags += ['-DHAVE_EPOLL'] if linux else ['-DHAVE_KQUEUE']
    for variant in ['original', 'patched', 'disabled']:
        if variant == 'patched':
            for module, entries in [('buffer', buffer_patches), ('reactor', manifest['patches'])]:
              for entry in entries:
                patch = ROOT/'migration/patches'/module/entry['path']
                if hashlib.sha256(patch.read_bytes()).hexdigest() != entry['sha256']:
                    raise ValueError('Patch checksum differs')
                patch_proofs.append(apply_patch_verified(tree,patch,entry['upstream_paths'],entry['sha256']))
            flags += ['-DSWOOLE_RS_BUFFER=1', '-I'+str(ROOT/'native/include'), '-I'+str(ROOT/'native/buffer')]
        for name in [*backends, 'stream']:
            selected_flags = [flag for flag in flags if variant != 'disabled' or flag != '-DSWOOLE_RS_REACTOR']
            cmd = ['c++', *selected_flags, '-c', str(tree/(('src/network/' if name == 'stream' else 'src/reactor/')+name+'.cc')), '-o', str(tree/(variant+'-'+name+'.o'))]
            result = subprocess.run(cmd, capture_output=True, text=True)
            passed = result.returncode == 0 if variant != 'disabled' else (result.returncode != 0 and 'Reactor overlay requires --enable-swoole-rs-reactor' in result.stderr)
            print(variant, name, result.returncode, 'PASS' if passed else 'FAIL', flush=True)
            rows.append(dict(variant=variant, backend=name, command=cmd, returncode=result.returncode, passed=passed, stderr=result.stderr))
a.report.parent.mkdir(parents=True, exist_ok=True)
a.report.write_text(json.dumps(dict(pin=PIN, staged_inputs=inputs, patch_application=patch_proofs, compiler=subprocess.check_output(['c++', '--version'], text=True).splitlines()[0], rows=rows), indent=2)+'\n')
raise SystemExit(any(not row['passed'] for row in rows))

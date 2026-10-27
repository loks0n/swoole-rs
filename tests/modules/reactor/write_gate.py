#!/usr/bin/env python3
"""Compare actual queue-admission bodies with native send/allocation callbacks."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from ordered_gate import ROOT, PIN, block, apply_patch_verified
from tools.harness import archive_libs

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=Path, required=True)
p.add_argument('--archive', type=Path, required=True)
p.add_argument('--report', type=Path, required=True)
p.add_argument('--sanitize', action='store_true')
a = p.parse_args()
manifest = json.loads((ROOT/'migration/patches/reactor/manifest.json').read_text())
paths = sorted({name for patch in manifest['patches'] for name in patch['upstream_paths']})
with tempfile.TemporaryDirectory(prefix='swr-reactor-write-') as tmp:
    tree = Path(tmp)
    originals = {}
    for name in paths:
        originals[name] = subprocess.check_output(['git', '-C', str(a.source), 'show', PIN+':'+name], text=True)
        out = tree/name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(originals[name])
    applications = []
    for entry in manifest['patches']:
        path = ROOT/'migration/patches/reactor'/entry['path']
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('Patch checksum differs')
        applications.append(apply_patch_verified(tree, path, entry['upstream_paths'], entry['sha256']))
    bodies = []
    for variant, text in enumerate([originals['src/reactor/base.cc'], (tree/'src/reactor/base.cc').read_text()]):
        methods = []
        for name in ['write_func', '_write', '_writev']:
            body, _ = block(text, text.index('ssize_t Reactor::'+name+'('))
            methods.append(body.replace('ssize_t Reactor::'+name+'(', 'static ssize_t '+name+'('))
        bodies.append('struct Write'+str(variant)+' {\n'+'\n'.join(methods)+'\n};')
    (tree/'write.inc').write_text('\n'.join(bodies))
    text = subprocess.check_output(['git', '-C', str(a.source), 'show', PIN+':include/swoole_buffer.h'], text=True)
    body, _ = block(text, text.index('static bool empty(const Buffer *buffer)'))
    (tree/'empty.inc').write_text(body)
    exe = tree/'write'
    cmd = ['c++', '-std=c++14', '-O2', '-g', '-I'+str(tree), '-I'+str(ROOT/'native/reactor'), str(ROOT/'tests/modules/reactor/write_gate.cc'), str(a.archive.resolve()), '-o', str(exe), '-lpthread']
    if a.sanitize:
        cmd += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    if sys.platform.startswith('linux'):
        cmd += ['-ldl', '-lm']
    cmd+=archive_libs()
    subprocess.run(cmd, check=True)
    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
    print(result.stdout, end='')
    print(result.stderr, end='')
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(dict(patch_application=applications, pin=PIN, patch_manifest=manifest, 
                                      compiler=subprocess.check_output(['c++', '--version'], text=True).splitlines()[0], command=cmd,
                                      scope='actual original/selected write_func + original Buffer::empty predicate; native allocation/socket/send/catch/append facades', returncode=result.returncode, stdout=result.stdout, stderr=result.stderr), indent=2)+'\n')
    raise SystemExit(result.returncode)

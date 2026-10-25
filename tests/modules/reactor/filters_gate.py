#!/usr/bin/env python3
"""Compare complete pinned/selected kqueue add/set/del with native syscall faults."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from ordered_gate import ROOT, PIN, block, apply_patch_verified

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=Path, required=True)
p.add_argument('--archive', type=Path, required=True)
p.add_argument('--report', type=Path, required=True)
p.add_argument('--sanitize', action='store_true')
a = p.parse_args()
patch = ROOT/'migration/patches/reactor/0001-readiness-policy.patch'
entry = json.loads((patch.parent/'manifest.json').read_text())['patches'][0]
paths = entry['upstream_paths']
with tempfile.TemporaryDirectory(prefix='swr-reactor-filters-') as tmp:
    tree = Path(tmp)
    original = {}
    for name in paths:
        original[name] = subprocess.check_output(['git', '-C', str(a.source), 'show', PIN+':'+name], text=True)
        out = tree/name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(original[name])
    application = apply_patch_verified(tree, patch, paths, entry['sha256'])
    helpers = []
    for name in ['isset_read_event', 'isset_write_event']:
        text = original['include/swoole_reactor.h']
        body, _ = block(text, text.index('static bool '+name+'('))
        helpers.append(body)
    classes = ['struct Reactor {\n'+'\n'.join(helpers)+'\n};']
    for variant, text in enumerate([original['src/reactor/kqueue.cc'], (tree/'src/reactor/kqueue.cc').read_text()]):
        methods = []
        for method in ['add', 'set', 'del']:
            body, _ = block(text, text.index('int ReactorKqueue::'+method+'('))
            # Replace only the native executor/type boundary, not branch policy.
            body = body.replace('ReactorKqueue::', '').replace('struct kevent', 'struct TestKevent').replace('::kevent(', 'native_kevent(').replace('EV_SET(', 'TEST_EV_SET(')
            methods.append(body)
        classes.append('struct Filters'+str(variant)+': FiltersBase {\n'+'\n'.join(methods)+'\n};')
    (tree/'filters.inc').write_text('\n'.join(classes))
    exe = tree/'filters'
    cmd = ['c++', '-std=c++14', '-O2', '-g', '-I'+str(tree), '-I'+str(ROOT/'native/reactor'), str(ROOT/'tests/modules/reactor/filters_gate.cc'), str(a.archive.resolve()), '-o', str(exe), '-lpthread']
    if a.sanitize:
        cmd += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    if sys.platform.startswith('linux'):
        cmd += ['-ldl', '-lm']
    subprocess.run(cmd, check=True)
    result = subprocess.run([str(exe)], capture_output=True, text=True)
    print(result.stdout, end='')
    print(result.stderr, end='')
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(dict(patch_application=[application], pin=PIN,
                                      compiler=subprocess.check_output(['c++', '--version'], text=True).splitlines()[0], command=cmd,
                                      scope='actual complete original/patched kqueue add/set/del, native executor+logging facades', returncode=result.returncode, stdout=result.stdout, stderr=result.stderr), indent=2)+'\n')
    raise SystemExit(result.returncode)

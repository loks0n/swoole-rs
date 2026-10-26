#!/usr/bin/env python3
"""Ordinary public String operations: original vs selected, exact positive assertion count."""
import argparse
import io
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import uuid
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.build_hybrid import apply_patch_verified
from tools.harness import run_compiler
from tools.harness import run_isolated
from tools.build_upstream import COMMIT as PIN

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--sanitize', action='store_true')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists(): raise ValueError('Unique report required; preserve every initial outcome')
    a.output.parent.mkdir(parents=True, exist_ok=True)
    report = dict(assigned_to='@loks0n', passed=False, scope='Ordinary no-custom append/write/i32/repeat/copy/termination/reduce; no POP/lifetime/fault/custom effect',
                  source_pin=PIN, free_bytes=shutil.disk_usage(a.output.parent).free,
                  guard_bytes=4*1024**3, profiles={}, whole_parity=False)
    def save(): a.output.write_text(json.dumps(report, indent=2)+'\n')
    if report['free_bytes'] < report['guard_bytes']:
        report['status']='GUARD_REFUSED';save();return 1
    work = a.output.parent / ('compatibility-'+uuid.uuid4().hex);work.mkdir()
    report['workdir']=str(work)
    data=subprocess.check_output(['git','-C',str(a.source),'archive',PIN,'include','src/core/string.cc','src/core/base.cc','src/os/base.cc','src/core/base64.cc'])
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for member in archive:
            if member.isfile():
                path=work/member.name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(archive.extractfile(member).read())
    def guard():
        free=shutil.disk_usage(work).free
        report.setdefault('preflights',[]).append(free)
        if free < report['guard_bytes']:
            report['status']='GUARD_REFUSED';save();raise RuntimeError('Unchanged4GiB guard refused compile')
    layout=work/'layout.c'
    layout.write_text('#include "swoole_rs_string.h"\n_Static_assert(sizeof(swr_v1_string_compat_cursor)==80,"cursor");\n_Static_assert(offsetof(swr_v1_string_compat_cursor,digits)==68,"digits");\n_Static_assert(sizeof(swr_v1_string_compat_step_result)==56,"step");\n_Static_assert(offsetof(swr_v1_string_compat_step_result,mask)==52,"mask");\n')
    cmd=['cc','-std=c11','-Werror','-fsyntax-only','-I'+str(ROOT/'native/buffer'),str(layout)]
    guard();r=run_isolated(cmd,timeout=30);report['c11']={'command':cmd,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
    if r.returncode:save();return 1
    local=Path(__file__).resolve().parent
    flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','openssl'],text=True))
    for engine in ['original','selected']:
        if engine=='selected':
            manifest=ROOT/'migration/patches/buffer/manifest.json';entry=json.loads(manifest.read_text())['patches'][2]
            report['application']=apply_patch_verified(work,manifest.parent/entry['path'],entry['upstream_paths'],entry['sha256'])
        cmd=['c++','-std=c++17','-O1','-g','-ffunction-sections','-fdata-sections','-I'+str(work/'include'),'-I'+str(ROOT/'native/buffer'),
             *[str(work/name) for name in ['src/core/string.cc','src/core/base.cc','src/os/base.cc','src/core/base64.cc']],str(local/'compatibility.cc'),*flags]
        if engine=='selected':
            cmd.append(str(a.archive.resolve()))
        cmd+=['-Wl,-dead_strip' if sys.platform=='darwin' else '-Wl,--gc-sections','-lm']
        if sys.platform.startswith('linux'):cmd+=['-ldl','-lpthread','-lrt','-lutil']
        if a.sanitize:cmd+=['-fsanitize=address,undefined','-fno-sanitize-recover=all']
        binary=work/engine;cmd+=['-o',str(binary)]
        row=report['profiles'][engine]={'command':cmd}
        guard()
        row['compile']=run_compiler(cmd)
        if row['compile']['returncode']:save();return 1
        r=run_isolated([str(binary)],timeout=30);row['run']={'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
        if r.returncode:save();return 1
        row['outcome']=json.loads(r.stdout.splitlines()[-1])
        if row['outcome']!={'checks':44,'profile':'ordinary-no-custom-no-pop'}:
            report['error']='Exact positive assertion inventory differs';save();return 1
        if engine=='selected':
            symbols=subprocess.check_output(['nm','-g',str(binary)],text=True)
            row['compat_export_present']='swr_v1_string_compat_step' in symbols
            if not row['compat_export_present']:save();return 1
            report['selected_whole_tu_syntax']=[]
            for standard in ['c++14','c++17','c++20']:
                command=['c++','-std='+standard,'-fsyntax-only','-I'+str(work/'include'),'-I'+str(ROOT/'native/buffer'),*shlex.split(subprocess.check_output(['pkg-config','--cflags','openssl'],text=True)),str(work/'src/core/string.cc')]
                command+=['-O2','-fstrict-aliasing']
                guard();r=run_isolated(command,timeout=30);report['selected_whole_tu_syntax'].append({'command':command,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
                if r.returncode:save();return 1
        save()
    report['passed']=True;report['status']='PASS';save();print(json.dumps({'passed':True,'profiles':2,'checks_per_profile':44}));return 0
if __name__=='__main__':raise SystemExit(main())

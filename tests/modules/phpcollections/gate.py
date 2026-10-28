#!/usr/bin/env python3
"""Actual pinned Table count bodies plus bounded Table policy comparison."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.build_upstream import require_build_space
from tools.harness import run_isolated,write_report
from tools.build_upstream import COMMIT as PIN

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def snapshot_inputs(work):
    paths=[ROOT/'crates/phpcollections/src/lib.rs',ROOT/'native/phpcollections/swoole_rs_phpcollections.h',
           *[Path(__file__).with_name(name) for name in ['gate.cc','arithmetic.cc','write.cc']]]
    # Read everything before writing, then compile from private copies so the
    # retained work directory reproduces a failure.
    contents=[(path,path.read_bytes()) for path in paths]
    target=work/'inputs';target.mkdir()
    result={}
    for source,data in contents:
        copied=target/source.name;copied.write_bytes(data)
        result[source.name]=copied
    return result

def stage(source, work):
    result={}
    manifest=json.loads((ROOT/'migration/patches/phpcollections/manifest.json').read_text())
    if manifest['upstream_commit'] != PIN:raise ValueError('Overlay pin differs')
    for patch in manifest['patches']:
        p=ROOT/'migration/patches/phpcollections'/patch['path']
        if sha(p)!=patch['sha256']:raise ValueError('Patch checksum differs')
        for name in patch['upstream_paths']:
            original=subprocess.check_output(['git','-C',str(source),'show',PIN+':'+name])
            target=work/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(original)
        env={**os.environ,'GIT_CEILING_DIRECTORIES':str(work.parent.resolve())}
        subprocess.run(['git','apply','--check',str(p)],cwd=work,env=env,check=True,capture_output=True)
        subprocess.run(['git','apply',str(p)],cwd=work,env=env,check=True,capture_output=True)
        for name in patch['upstream_paths']:result[name]={}
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--archive',type=Path)
    p.add_argument('--library-kind',choices=['staticlib','cdylib'],default='staticlib',help='Standalone only; immutable --archive takes precedence')
    p.add_argument('--sanitizers',action='store_true',help='C++ witness frames only; Rust/native PHP runtime are not instrumented')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    output=a.output.resolve();work=output.parent/('phpcollections-'+uuid.uuid4().hex);work.mkdir(parents=True)
    r={'passed':False,'pin':PIN,'scope':__doc__,'work':str(work),'commands':[],
       'library_mode':'external_selected_archive' if a.archive else a.library_kind,
       'sanitizer_scope':'C++ scalar and scripted-effect witness frames only; Rust and real PHP not instrumented' if a.sanitizers else 'none',
}
    def run(cmd):
        require_build_space(ROOT);require_build_space(work)
        x=run_isolated(list(map(str,cmd)),timeout=90)
        r['commands'].append(dict(command=list(map(str,cmd)),returncode=x.returncode,stdout=x.stdout,stderr=x.stderr));write_report(output,r)
        if x.returncode:raise ValueError('Command failed; preserve first receipt')
        return x
    try:
        inputs=snapshot_inputs(work)
        stage(a.source,work)
        for engine in ['native','selected']:
            def text(name):return (subprocess.check_output(['git','-C',str(a.source),'show',PIN+':ext-src/'+name],text=True) if engine=='native' else (work/'ext-src'/name).read_text())
            table=text('swoole_table.cc');begin=table.index('    if (mode == COUNT_NORMAL)') if engine=='native' else table.index('    size_t column_count = 0;')
            end=table.index('\n}',begin)
            (work/(engine+'-count.inc')).write_text(table[begin:end])
            arithmetic=[]
            signatures=(['static inline bool table_read_field_value(', 'static void table_update('] if engine=='selected' else []) + ['static PHP_METHOD(swoole_table, '+method+')' for method in ['incr','decr']] + [('static inline bool table_row2array(' if engine=='selected' else 'static inline void table_row2array('), ('static inline bool table_get_field_value(' if engine=='selected' else 'static inline void table_get_field_value(')]
            for signature in signatures:
                begin=table.rindex(signature);opening=table.index('{',begin);end=opening+1;depth=1
                while depth:
                    depth+=(table[end]=='{')-(table[end]=='}');end+=1
                arithmetic.append(table[begin:end])
            (work/(engine+'-arithmetic.inc')).write_text('\n'.join(arithmetic))
            writes=[]
            signatures=(['static inline bool table_set_field_value('] if engine=='selected' else []) + ['static PHP_METHOD(swoole_table, set)']
            for signature in signatures:
                begin=table.rindex(signature);opening=table.index('{',begin);end=opening+1;depth=1
                while depth:
                    depth+=(table[end]=='{')-(table[end]=='}');end+=1
                writes.append(table[begin:end])
            (work/(engine+'-write.inc')).write_text('\n'.join(writes))
        archive=a.archive.resolve() if a.archive else work/('libphpcollections.a' if a.library_kind=='staticlib' else ('libphpcollections.dylib' if sys.platform=='darwin' else 'libphpcollections.so'))
        if not a.archive:
            tests=work/'rust-tests';run(['rustc','--edition=2024','--test',inputs['lib.rs'],'-o',tests]);run([tests])
            run(['rustc','--edition=2024','--crate-type='+a.library_kind,'-C','opt-level=2',inputs['lib.rs'],'-o',archive])
        binary=work/'gate';cmd=['c++','-std=c++17','-O2','-UNDEBUG','-Wall','-Wextra','-Werror','-I'+str(work),'-I'+str(work/'inputs'),inputs['gate.cc'],archive,'-lpthread','-lm','-o',binary]
        if a.sanitizers:cmd+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
        if sys.platform.startswith('linux'):cmd+=['-ldl','-lrt','-lutil']
        if not a.archive and a.library_kind=='cdylib':cmd+=['-Wl,-rpath,'+str(work)]
        run(cmd);r['observations']=json.loads(run([binary]).stdout)
        arithmetic=work/'arithmetic';cmd[cmd.index(inputs['gate.cc'])]=inputs['arithmetic.cc'];cmd[cmd.index(binary)]=arithmetic
        run(cmd);r['arithmetic_observations']=json.loads(run([arithmetic]).stdout)
        write=work/'write';cmd[cmd.index(inputs['arithmetic.cc'])]=inputs['write.cc'];cmd[cmd.index(arithmetic)]=write
        run(cmd);r['write_observations']=json.loads(run([write]).stdout)
        r['passed']=True
    except Exception as e:
        r['error']=str(e)
        if isinstance(e,subprocess.CalledProcessError):r['stderr']=str(e.stderr)
    write_report(output,r);print(json.dumps({k:r.get(k) for k in ['passed','error','work']}));return int(not r['passed'])
if __name__=='__main__':sys.exit(main())

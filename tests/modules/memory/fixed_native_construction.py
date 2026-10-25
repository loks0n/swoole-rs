#!/usr/bin/env python3
"""Actual FixedPool constructor/queue bodies with inert success effects, not Native allocator/IPC/failure proof."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.build_hybrid import apply_patch_verified
from tools.harness import run_isolated
PIN='8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e'
SOURCE='src/memory/fixed_pool.cc'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cxx',default='c++')
    args=parser.parse_args()
    if args.output.exists():
        parser.error('Refusing to overwrite a receipt')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    report={'passed':False,'scope':__doc__,'upstream_commit':PIN,'commands':[],
            'rust_archive_instrumented':False,'archive_source_correspondence':'Caller supplies exact source-qualified immutable archive; ABI presence is not correspondence proof',
            'unqualified':['actual Native allocator/shared memory','failure/IPC/fork/thread/lifetime stress','Linux','full production/original inventories','performance/default activation']}
    try:
        archive=args.archive.resolve(strict=True)
        report['archive_sha256']=sha(archive)
        report['source_sha256']={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),Path(__file__).with_suffix('.cc'),ROOT/'native/memory/swoole_rs_memory.h']}
        manifest=json.loads((ROOT/'migration/patches/memory/manifest.json').read_text())
        assert manifest['upstream_commit']==PIN
        entry=next(e for e in manifest['patches'] if SOURCE in e['upstream_paths'])
        report['patch']=entry
        def pinned(name):
            return subprocess.check_output(['git','-C',str(args.source),'show',PIN+':'+name],timeout=20).decode()
        with tempfile.TemporaryDirectory(prefix='swr-fixed-native-') as temporary:
            tree=Path(temporary);source=tree/SOURCE;source.parent.mkdir(parents=True)
            source.write_text(pinned(SOURCE))
            report['patch_application']=apply_patch_verified(tree,ROOT/'migration/patches/memory'/entry['path'],entry['upstream_paths'],entry['sha256'])
            selected=source.read_text();header=pinned('include/swoole_memory.h')
            declarations=header.split('namespace swoole {',1)[1].split('struct RingBufferImpl;',1)[0]
            bodies=selected.split('namespace swoole {',1)[1].rsplit('}  // namespace swoole',1)[0]
            model=tree/'fixed_native_construction_selected.inc'
            model.write_text('namespace fixture {\n'+declarations+bodies+'\n}\n')
            report['compiler']=subprocess.check_output([*shlex.split(args.cxx),'--version'],text=True)
            for standard in ['c++14','c++17']:
                binary=tree/standard
                command=[*shlex.split(args.cxx),'-std='+standard,'-O1','-g','-Wall','-Wextra','-Werror',
                         '-Wno-unused-parameter','-fsanitize=address,undefined','-fno-omit-frame-pointer',
                         '-I'+str(tree),'-I'+str(ROOT/'native/memory'),'-I'+str(ROOT/'native/include'),
                         str(Path(__file__).with_suffix('.cc')),str(archive),'-lpthread','-ldl','-lm','-o',str(binary)]
                for label,argv in [('compile',command),('inert-success',[str(binary)])]:
                    if label=='compile':
                        free={str(p):shutil.disk_usage(p).free for p in [ROOT,tree,args.output.parent]}
                        if min(free.values())<4*1024**3:
                            report['commands'].append({'case':standard+'-'+label,'blocked':'unchanged 4GiB guard','free_bytes':free})
                            raise RuntimeError('Compiler refused by unchanged 4GiB guard')
                    r=run_isolated(argv,cwd=ROOT,timeout=60)
                    report['commands'].append({'case':standard+'-'+label,'argv':argv,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
                    if r.returncode:
                        raise RuntimeError(standard+'-'+label+' failed')
                value=json.loads(r.stdout)
                assert value['passed'] and value['owned_cases']==24 and value['borrowed_cases']==60 and value['explicit_os_calls']==0
                report.setdefault('results',{})[standard]=value
            assert sha(archive)==report['archive_sha256']
            assert all(sha(ROOT/p)==expected for p,expected in report['source_sha256'].items())
            report['passed']=True
    except Exception as error:
        report['error']=str(error)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report.get(k) for k in ['passed','error','results']}))
    return int(not report['passed'])


if __name__=='__main__':
    sys.exit(main())

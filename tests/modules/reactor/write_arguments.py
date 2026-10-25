#!/usr/bin/env python3
"""Exact _write/_writev consumer bodies with normal Socket/Buffer effect facades.

Positive byte/vector lengths and full/partial successful sends; genuine target
POSIX iovec layout proof. No Native SSL rejection, faults, allocation/failure,
lifetime/stopped probes, actual kernel/loaded production or performance claim.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from ordered_gate import ROOT,PIN,block
sys.path.insert(0,str(ROOT))
from tools.build_hybrid import apply_patch_verified
from tools.build_upstream import require_build_space
from tools.harness import run_isolated
from tools.harness import run_compiler
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source',type=Path,required=True);p.add_argument('--archive',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--sanitize',action='store_true');a=p.parse_args()
if a.report.exists():raise ValueError('Choose a unique receipt path')
report=dict(scope=__doc__,pin=PIN,patch_application=[],commands=[],results=[],passed=False)
with tempfile.TemporaryDirectory(prefix='swr-write-arguments-') as tmp:
    t=Path(tmp);m=ROOT/'migration/patches/reactor/manifest.json';entries=json.loads(m.read_text())['patches'];original={}
    for e in entries:
        for name in e['upstream_paths']:
            if name not in original:
                data=subprocess.check_output(['git','-C',str(a.source),'show',PIN+':'+name]);original[name]=data.decode();path=t/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    for e in entries:report['patch_application'].append(apply_patch_verified(t,m.parent/e['path'],e['upstream_paths'],e['sha256']))
    try:
        for variant in ['original','selected']:
            base=original['src/reactor/base.cc'] if variant=='original' else (t/'src/reactor/base.cc').read_text()
            cls='''
            class Reactor {public:mutable Buffer buffer;
                static ssize_t _write(Reactor*,Socket*,const void*,size_t);
                static ssize_t _writev(Reactor*,Socket*,const iovec*,size_t);
                static ssize_t write_func(const Reactor *r,Socket*,const size_t n,const std::function<ssize_t()> &send,const std::function<void(Buffer*)> &append){
                    auto sent=send();assert(sent>0&&static_cast<size_t>(sent)<=n);
                    if(static_cast<size_t>(sent)<n)append(&r->buffer);
                    return static_cast<ssize_t>(n);
                }
            };
'''
            for sig in ['ssize_t Reactor::_write(','ssize_t Reactor::_writev(']:cls+=block(base,base.index(sig))[0]+'\n'
            (t/'write_arguments.inc').write_text(cls);binary=t/variant
            cmd=['c++','-std=c++14','-O1','-g','-I'+str(t),'-I'+str(ROOT/'native/reactor'),ROOT/'tests/modules/reactor/write_arguments.cc',a.archive.resolve(),'-lpthread','-o',binary]
            if a.sanitize:cmd+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
            if sys.platform.startswith('linux'):cmd+=['-ldl','-lm']
            for stage,command in [('compile',cmd),('execute',[binary])]:
                require_build_space(ROOT);require_build_space(t)
                result=run_compiler(command, timeout=60) if stage=='compile' else vars(run_isolated(list(map(str,command)),cwd=t,timeout=60))
                report['commands'].append(dict(variant=variant,stage=stage,command=list(map(str,command)),exit=result['returncode'],stdout=result['stdout'],stderr=result['stderr'],cache={k:result[k] for k in ['cache_hit','cache_key','cache_reason'] if k in result}))
                if result['returncode'] or result['stderr']:raise RuntimeError(variant+' '+stage+' failed or warned')
            report['results'].append(dict(variant=variant,observations=json.loads(result['stdout'])))
        if report['results'][0]['observations']!=report['results'][1]['observations']:raise RuntimeError('Native/selected observations differ')
        report['passed']=True
    except Exception as error:report['error']=str(error)
a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k) for k in ['passed','error','results']}));raise SystemExit(not report['passed'])

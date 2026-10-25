#!/usr/bin/env python3
"""Actual C++ iterator operators vs frozen selected Native metadata policy only.

Inert keys/live tokens, ordinary pre/post traversal/copy/comparison, no callbacks,
Socket/syscall, allocation failure, invalidation/reentry or lifetime probes.
Original Native map order is qualified separately by unchanged sockets.py.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.build_upstream import require_build_space
from tools.harness import run_compiler
from tools.harness import run_isolated
CONTROL='e2c481325ffd35a3a9c6d041151aedb48a64c464'
HEADER='native/reactor/swoole_rs_reactor_sockets.h'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--sanitize',action='store_true')
    a=p.parse_args()
    if a.report.exists():raise ValueError('Choose unique receipt path')
    original=subprocess.check_output(['git','-C',str(ROOT),'show',CONTROL+':'+HEADER])
    captured=original.decode().replace('SWOOLE_RS_REACTOR_SOCKETS_H','SWR_ITERATOR_CONTROL_H')
    namespace='namespace swoole {\nnamespace network { struct Socket; }'
    if captured.count(namespace)!=1:raise ValueError('Frozen Native control namespace changed')
    captured=captured.replace(namespace,'namespace native_iterator_control {\nnamespace network { using Socket=::swoole::network::Socket; }')
    report=dict(owner='@loks0n',scope=__doc__,control_ref=CONTROL,control_header=original.decode(),commands=[],observations=[],passed=False,actual_production_SDK=False,actual_production_runtime=False,Linux=False,performance=False)
    try:
        with tempfile.TemporaryDirectory(prefix='swr-iterator-') as temporary:
            tree=Path(temporary);(tree/'iterator-control.h').write_text(captured)
            for standard in ['c++14','c++17','c++20']:
                for optimization in ['-O0','-O2']:
                    require_build_space(ROOT);require_build_space(tree)
                    binary=tree/(standard+optimization)
                    command=['c++','-std='+standard,optimization,'-g','-Werror','-DSWOOLE_RS_REACTOR=1','-DSWOOLE_RS_REACTOR_SOCKETS_OWNED=1','-I'+str(ROOT/'native/reactor'),'-I'+str(tree),str(ROOT/'tests/modules/reactor/socket_iterators.cc'),str(a.archive.resolve()),'-lpthread','-o',str(binary)]
                    if a.sanitize:command+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
                    if sys.platform.startswith('linux'):command+=['-ldl','-lm']
                    for stage,cmd in [('compile',command),('execute',[str(binary)])]:
                        result=run_compiler(cmd) if stage=='compile' else vars(run_isolated(cmd,cwd=tree,timeout=30))
                        report['commands'].append(dict(standard=standard,optimization=optimization,stage=stage,command=cmd,**result))
                        if result['returncode'] or result['stderr']:raise RuntimeError(stage+' failed/warned')
                    report['observations'].append(dict(standard=standard,optimization=optimization,result=json.loads(result['stdout'])))
            report['passed']=True
    except Exception as error:report['error']=str(error)
    finally:
        a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(passed=report['passed'],profiles=len(report['observations']),error=report.get('error'))))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())

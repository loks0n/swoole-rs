#!/usr/bin/env python3
"""Compile-only registry capability refusals, never constructs or executes an owner."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
from ordered_gate import ROOT
from tools.build_upstream import require_build_space

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    if a.report.exists():raise ValueError('Choose a unique report path')
    report=dict(scope=__doc__,assigned_to='@loks0n',commands=[],passed=False)
    profiles=[('default','',[],None),('explicit-off','',['-DSWOOLE_RS_REACTOR_SOCKETS_OWNED=0'],None),('known','',['-DSWOOLE_RS_REACTOR=1','-DSWOOLE_RS_REACTOR_SOCKETS_OWNED=1'],None),('missing-module','',['-DSWOOLE_RS_REACTOR_SOCKETS_OWNED=1'],'Socket registry requires --enable-swoole-rs-reactor'),('unknown-platform','#undef __APPLE__\n',['-DSWOOLE_RS_REACTOR=1','-DSWOOLE_RS_REACTOR_SOCKETS_OWNED=1'],'unknown policy is activation-blocked'),('unknown-version','#undef _LIBCPP_VERSION\n#define _LIBCPP_VERSION 999999\n',['-DSWOOLE_RS_REACTOR=1','-DSWOOLE_RS_REACTOR_SOCKETS_OWNED=1'],'unknown policy is activation-blocked'),('unknown-abi','#undef _LIBCPP_ABI_VERSION\n#define _LIBCPP_ABI_VERSION 9\n',['-DSWOOLE_RS_REACTOR=1','-DSWOOLE_RS_REACTOR_SOCKETS_OWNED=1'],'unknown policy is activation-blocked')]
    try:
        with tempfile.TemporaryDirectory(prefix='swr-registry-policy-') as temporary:
            for name,condition,flags,expected in profiles:
                source=Path(temporary)/(name+'.cc')
                source.write_text('#include "swoole_rs_reactor.h"\n#include <iterator>\n#include <new>\n#include <utility>\n#include <cstdlib>\n'+condition+'#include "swoole_rs_reactor_sockets.h"\n')
                require_build_space(ROOT);command=['c++','-std=c++14','-Werror','-I'+str(ROOT/'native/reactor'),*flags,'-fsyntax-only',str(source)];result=subprocess.run(command,text=True,capture_output=True)
                passed=(result.returncode==0 and not result.stderr) if expected is None else result.returncode!=0 and expected in result.stderr
                report['commands'].append(dict(profile=name,command=command,expected_diagnostic=expected,expectation_met=passed,exit=result.returncode,stdout=result.stdout,stderr=result.stderr))
                if not passed:raise RuntimeError(name+' did not satisfy its explicit compile/refusal contract')
        report['passed']=True
    except Exception as error:report['error']=str(error)
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({key:report.get(key) for key in ['passed','error']}));return int(not report['passed'])
if __name__=='__main__':raise SystemExit(main())

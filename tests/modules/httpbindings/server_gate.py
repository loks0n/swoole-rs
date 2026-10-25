#!/usr/bin/env python3
"""Actual normal-server receive controller and coroutine handler/accept loops."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from source import definition
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'http'))
from gate import PIN
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT,run_isolated,write_report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--archive',type=Path)
    group.add_argument('--rust-sanitize',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();local=Path(__file__).resolve().parent
    patches=[ROOT/'migration/patches/httpbindings'/n for n in ['0004-server-policy.patch','0005-coro-server-policy.patch']]
    report={'pin':PIN,'scope':__doc__,'limitations':'Native Zend/socket/parser/callback facades and bounded single-iteration accept loop; not actual Zend GC/bailout/coroutine IO/PHP or complete binding parity. Real native container order and callback identity retained. Native receive cleanup actually deletes fake contexts after the second captured-object release.', 'native_sanitizers':True,'rust_instrumented':args.rust_sanitize,'rust_std_instrumented':False,'passed':False}
    with tempfile.TemporaryDirectory(prefix='swr-httpbindings-server-') as temp:
        tree=Path(temp)
        if args.rust_sanitize:
            args.archive=tree/'libhttpbindings-asan.a'
            cmd=['rustc','--edition=2024','-Zsanitizer=address','--crate-type=staticlib','-C','opt-level=3','-C','panic=abort',str(ROOT/'crates/httpbindings/src/lib.rs'),'-o',str(args.archive)]
            r=run_isolated(cmd,timeout=60,env={**os.environ,'RUSTC_BOOTSTRAP':'1'});report['rust_compile']={'command':cmd,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
            if r.returncode:write_report(args.output,report);return 1
        names=['ext-src/swoole_http_server.cc','ext-src/swoole_http_server_coro.cc','include/swoole.h'];original={}
        for n in names:
            p=tree/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(subprocess.check_output(['git','-C',str(args.source),'show',PIN+':'+n]));original[n]=p.read_text()
        for p in patches:
            subprocess.run(['git','apply','--check',str(p)],cwd=tree,check=True);subprocess.run(['git','apply',str(p)],cwd=tree,check=True)
        helper=definition(original[names[2]],'static inline unsigned int swoole_str_istarts_with(')
        for namespace,texts in [('upstream_server',original),('candidate_server',{n:(tree/n).read_text() for n in names[:2]})]:
            receive=definition(texts[names[0]],'int php_swoole_http_server_onReceive(')
            handler=definition(texts[names[1]],'zend::Callable *get_handler(').replace('zend::Callable *get_handler(','zend::Callable *HandlerServer::get_handler(',1).replace('const HttpContext *ctx','const RouteContext *ctx')
            start=definition(texts[names[1]],'static PHP_METHOD(swoole_http_server_coro, start)')
            loop=definition(start,'    while (hs->running)')
            accept='void call_accept(AcceptSocket*sock,AcceptServer*hs){int fci_cache=0;Callback zcallback;\n'+loop+'\n}'
            p=tree/(namespace+'.cc');p.write_text('#include "server_oracle.h"\n'+helper+'\nnamespace '+namespace+'{\n'+receive+'\n'+handler+'\n'+accept+'\n}\n')
        binary=tree/'gate';cmd=['c++','-std=c++14','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(local),'-I'+str(ROOT/'native/httpbindings'),str(tree/'upstream_server.cc'),str(tree/'candidate_server.cc'),str(local/'server_gate.cc'),str(args.archive.resolve()),'-lm','-o',str(binary)]
        if sys.platform.startswith('linux'):cmd+=['-ldl','-lpthread','-lrt','-lutil']
        report['compile_command']=cmd;r=run_isolated(cmd,timeout=60);report['compile']={'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
        if not r.returncode:
            symbols=subprocess.check_output(['nm','-g',str(binary)],text=True)
            assert all(s in symbols for s in ['swr_v1_httpbindings_receive','swr_v1_httpbindings_handler','swr_v1_httpbindings_accept'])
            r=run_isolated([str(binary)],timeout=90);report['run']={'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
            if not r.returncode:report['outcome']=json.loads(r.stdout.splitlines()[-1]);report['passed']=True
        write_report(args.output,report)
        print(json.dumps(report.get('outcome',report.get('run',report['compile']))))
        return 0 if report['passed'] else 1


if __name__=='__main__':sys.exit(main())

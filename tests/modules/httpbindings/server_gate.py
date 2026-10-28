#!/usr/bin/env python3
"""Actual coroutine-server handler routing and accept loop."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from source import definition, rust_declarations
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'http'))
from gate import PIN
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from tools.build_hybrid import hybrid_tree
from tools.harness import ROOT,run_isolated,write_report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--archive',type=Path,required=True,help='Rust archive of the hybrid build under test')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();local=Path(__file__).resolve().parent
    report={'pin':PIN,'scope':__doc__,'limitations':'Native Zend/socket/callback facades and bounded single-iteration accept loop; not actual Zend GC/bailout/coroutine IO/PHP or complete binding parity. Real native container order and callback identity retained.', 'native_sanitizers':True,'rust_instrumented':False,'passed':False}
    with tempfile.TemporaryDirectory(prefix='swr-httpbindings-server-') as temp:
        tree=Path(temp)
        # Upstream side from the pin, candidate side from the hybrid build's fully patched tree.
        hybrid_source,hybrid_flags=hybrid_tree(args.archive)
        names=['ext-src/swoole_http_server_coro.cc','include/swoole.h']
        original={n:subprocess.check_output(['git','-C',str(args.source),'show',PIN+':'+n]).decode() for n in names}
        selected={n:(hybrid_source/n).read_text() for n in names}
        for namespace,texts in [('upstream_server',original),('candidate_server',selected)]:
            helper=definition(texts[names[1]],'static inline unsigned int swoole_str_istarts_with(')
            helper=rust_declarations(helper,hybrid_flags)+helper
            handler=definition(texts[names[0]],'zend::Callable *get_handler(').replace('zend::Callable *get_handler(','zend::Callable *HandlerServer::get_handler(',1).replace('const HttpContext *ctx','const RouteContext *ctx')
            start=definition(texts[names[0]],'static PHP_METHOD(swoole_http_server_coro, start)')
            loop=definition(start,'    while (hs->running)')
            accept='void call_accept(AcceptSocket*sock,AcceptServer*hs){int fci_cache=0;Callback zcallback;\n'+loop+'\n}'
            p=tree/(namespace+'.cc');p.write_text('#include "server_oracle.h"\n'+helper+'\nnamespace '+namespace+'{\n'+handler+'\n'+accept+'\n}\n')
        binary=tree/'gate';cmd=['c++','-std=c++14','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(local),'-I'+str(ROOT/'native/httpbindings'),*hybrid_flags,str(tree/'upstream_server.cc'),str(tree/'candidate_server.cc'),str(local/'server_gate.cc'),str(args.archive.resolve()),'-lm','-o',str(binary)]
        if sys.platform.startswith('linux'):cmd+=['-ldl','-lpthread','-lrt','-lutil']
        report['compile_command']=cmd;r=run_isolated(cmd,timeout=60);report['compile']={'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
        if not r.returncode:
            symbols=subprocess.check_output(['nm','-g',str(binary)],text=True)
            assert all(s in symbols for s in ['swr_v1_httpbindings_handler','swr_v1_httpbindings_accept'])
            r=run_isolated([str(binary)],timeout=90);report['run']={'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
            if not r.returncode:report['outcome']=json.loads(r.stdout.splitlines()[-1]);report['passed']=True
        write_report(args.output,report)
        print(json.dumps(report.get('outcome',report.get('run',report['compile']))))
        return 0 if report['passed'] else 1


if __name__=='__main__':sys.exit(main())

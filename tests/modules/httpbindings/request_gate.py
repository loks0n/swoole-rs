#!/usr/bin/env python3
"""Actual PHP request callbacks and response key policy with native effect facades."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from source import definition
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'http'))
from gate import PIN
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--archive', type=Path)
    group.add_argument('--rust-sanitize', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--without-compression', action='store_true')
    args = parser.parse_args()
    local = Path(__file__).resolve().parent
    patches = [ROOT/'migration/patches/httpbindings'/n for n in ['0002-request-policy.patch','0003-response-policy.patch']]
    report = {'pin': PIN, 'scope': __doc__, 'limitations': 'Zend/IO/callback helpers are ordered native facades, not actual PHP allocator, GC, bailout or complete binding parity. Preserves native pointer-size fast-token quirk, scratch writes, shrinking quote-trim bound and fragmented-header behavior.',
              'compression_compiled': not args.without_compression, 'native_sanitizers': True, 'rust_instrumented': args.rust_sanitize, 'rust_std_instrumented': False,
              'passed': False}
    with tempfile.TemporaryDirectory(prefix='swr-httpbindings-request-') as temp:
        tree = Path(temp)
        if args.rust_sanitize:
            args.archive=tree/'libhttpbindings-asan.a'
            command=['rustc','--edition=2024','-Zsanitizer=address','--crate-type=staticlib','-C','opt-level=3','-C','panic=abort',str(ROOT/'crates/httpbindings/src/lib.rs'),'-o',str(args.archive)]
            result=run_isolated(command,timeout=60,env={**os.environ,'RUSTC_BOOTSTRAP':'1'})
            report['rust_compile']={'command':command,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
            if result.returncode:write_report(args.output,report);return 1
        names=['ext-src/swoole_http_request.cc','ext-src/swoole_http_response.cc','include/swoole.h','include/swoole_util.h']
        original={}
        for name in names:
            p=tree/name;p.parent.mkdir(parents=True,exist_ok=True)
            p.write_bytes(subprocess.check_output(['git','-C',str(args.source),'show',PIN+':'+name]));original[name]=p.read_text()
        for patch in patches:
            subprocess.run(['git','apply','--check',str(patch)],cwd=tree,check=True)
            subprocess.run(['git','apply',str(patch)],cwd=tree,check=True)
        helpers='\n'.join(definition(original['include/swoole.h'],sig) for sig in ['static inline unsigned int swoole_strcaseeq(','static inline unsigned int swoole_str_istarts_with('])
        helpers+='\nnamespace swoole {\n'+'\n'.join(definition(original['include/swoole_util.h'],sig) for sig in ['static inline size_t ltrim(','static inline size_t rtrim(char *'])+'\n}\n'
        (tree/'helpers.h').write_text(helpers)
        for namespace,texts in [('upstream_request',original),('candidate_request',{n:(tree/n).read_text() for n in names[:2]})]:
            request=texts[names[0]];response=texts[names[1]]
            parts=[definition(request,sig) for sig in ['bool swoole_http_token_list_contains_value(','static inline char *http_trim_double_quote(','static int http_request_on_url(','static int http_request_on_header_value(']]
            parts.append(definition(response,'static inline void http_response_header_key_format('))
            exports='''int call_header(llhttp_t*p,const char*s,size_t n){return http_request_on_header_value(p,s,n);}
int call_url(llhttp_t*p,const char*s,size_t n){return http_request_on_url(p,s,n);}
char *call_trim(char*p,size_t*n){return http_trim_double_quote(p,n);}
void call_key(char*p,int n){http_response_header_key_format(p,n);}
'''
            p=tree/(namespace+'.cc');p.write_text('#include "request_oracle.h"\n#include "helpers.h"\nnamespace '+namespace+' {\n'+'\n'.join(parts)+'\n'+exports+'}\n')
        binary=tree/'gate'
        command=['c++','-std=c++14','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(local),'-I'+str(tree),'-I'+str(ROOT/'native/httpbindings'),str(tree/'upstream_request.cc'),str(tree/'candidate_request.cc'),str(local/'request_gate.cc'),str(args.archive.resolve()),'-lm','-o',str(binary)]
        if args.without_compression:command.append('-DSWR_HTTPBINDINGS_NO_COMPRESSION')
        if sys.platform.startswith('linux'):command+=['-ldl','-lpthread','-lrt','-lutil']
        report['compile_command']=command;result=run_isolated(command,timeout=60);report['compile']={'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
        if result.returncode==0:
            symbols=subprocess.check_output(['nm','-g',str(binary)],text=True)
            assert all(s in symbols for s in ['swr_v1_httpbindings_request_header','swr_v1_httpbindings_request_key','swr_v1_httpbindings_request_url','swr_v1_httpbindings_tokens','swr_v1_httpbindings_trim_quotes','swr_v1_httpbindings_response_key'])
            result=run_isolated([str(binary)],timeout=90);report['run']={'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
            if result.returncode==0:report['outcome']=json.loads(result.stdout.splitlines()[-1]);report['passed']=True
        write_report(args.output,report)
        if not report['passed']:print(json.dumps(report.get('run',report['compile'])),file=sys.stderr)
        else:print(json.dumps(report['outcome']))
        return 0 if report['passed'] else 1


if __name__=='__main__':sys.exit(main())

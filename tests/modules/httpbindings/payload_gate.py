#!/usr/bin/env python3
"""Actual pinned/patched payload callbacks, option body and compression methods."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from source import definition
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT, run_isolated, write_report
PIN='8e8c49915ca5f9dcb9ee654f9e336a9c88dd375e'
WRAPPERS=r'''
Result body(const Input&in,size_t fail){
 Oracle local;oracle=&local;HttpContext ctx;setup(ctx,in);
 std::string storage(in.previous,'p');storage+=in.bytes;storage+='\0';
 llhttp_t parser{&ctx};local.trace.clear();local.fail=fail;Result r;
 try{r.code=http_request_on_body(&parser,storage.data()+in.previous,in.bytes.size());}catch(const Exit&){r.exited=true;}
 if(ctx.request.body_at)r.offset=ctx.request.body_at-storage.data();return capture(ctx,r);
}
Result complete(const Input&in,size_t fail){
 Oracle local;oracle=&local;HttpContext ctx;setup(ctx,in);
 std::string storage(std::max(in.previous,in.bytes.size()),'p');std::copy(in.bytes.begin(),in.bytes.end(),storage.begin());storage+='\0';
 if(in.flags&8)ctx.request.body_at=storage.data();
 llhttp_t parser{&ctx};local.trace.clear();local.fail=fail;Result r;
 try{r.code=http_request_message_complete(&parser);}catch(const Exit&){r.exited=true;}
 return capture(ctx,r);
}
Result option(const std::string&key,zval value,size_t fail,bool reentry){
 Oracle local;oracle=&local;HttpContext ctx;local.fail=fail;Result r;
 if(reentry)local.hook=[&](const std::string&){ctx.parse_cookie=true;ctx.parse_files=true;ctx.compression_level=991;};
 try{apply_option(&ctx,key.data(),key.size(),&value);}catch(const Exit&){r.exited=true;}
 r.flags=ctx.parse_cookie|(ctx.parse_body?2:0)|(ctx.parse_files?4:0)|(ctx.enable_compression?8:0)|(ctx.websocket_compression?16:0);
 r.level=ctx.compression_level;r.directory=ctx.upload_tmp_dir;r.trace=local.trace;return r;
}
Result compression(const std::string&value,size_t n,int method){
 Oracle local;oracle=&local;HttpContext ctx;Result r;ctx.compression_method=method;
#ifdef SW_HAVE_COMPRESSION
 const char*encoding=ctx.get_content_encoding();r.encoding=encoding?encoding:"(null)";
 ctx.set_compression_method(value.data(),n);
#endif
 r.accepted=ctx.accept_compression;r.method=ctx.compression_method;return r;
}
'''

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--source',type=Path,required=True)
 group=parser.add_mutually_exclusive_group(required=True);group.add_argument('--archive',type=Path);group.add_argument('--rust-sanitize',action='store_true')
 parser.add_argument('--native-libc',action='store_true',help='Unsanitized native libc semantics; ASan interceptors can alter locale behavior')
 parser.add_argument('--locale',default='C')
 parser.add_argument('--capabilities',type=int,choices=range(8),default=7)
 parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();local=Path(__file__).resolve().parent
 report={'pin':PIN,'scope':__doc__,'limitations':'Native effect facades, not actual Zend allocator/GC/bailout. Compression capability0 compiles both original/candidate methods out; other profiles exercise the original methods.','capabilities':args.capabilities,'native_sanitizers':not args.native_libc,'locale':args.locale,'rust_instrumented':args.rust_sanitize,'rust_std_instrumented':False,'passed':False}
 with tempfile.TemporaryDirectory(prefix='swr-httpbindings-payload-')as temp:
  tree=Path(temp)
  if args.rust_sanitize:
   args.archive=tree/'rust.a';cmd=['rustc','--edition=2024','-Zsanitizer=address','--crate-type=staticlib','-C','opt-level=3','-C','panic=abort',str(ROOT/'crates/httpbindings/src/lib.rs'),'-o',str(args.archive)]
   r=run_isolated(cmd,timeout=60,env={**os.environ,'RUSTC_BOOTSTRAP':'1'});report['rust_compile']={'command':cmd,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
   if r.returncode:write_report(args.output,report);return 1
  original={n:subprocess.check_output(['git','-C',str(args.source),'show',PIN+':'+n]).decode()for n in ['ext-src/swoole_http_request.cc','include/swoole.h']}
  for n,text in original.items():p=tree/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
  patch=ROOT/'migration/patches/httpbindings/0002-request-policy.patch'
  subprocess.run(['git','apply','--check',str(patch)],cwd=tree,check=True);subprocess.run(['git','apply',str(patch)],cwd=tree,check=True)
  helpers='\n'.join(definition(original['include/swoole.h'],sig)for sig in ['static inline unsigned int swoole_strcaseeq(','static inline const char *swoole_strnstr(','static inline ssize_t swoole_strnpos('])
  (tree/'helpers.h').write_text('#define sw_likely(x) (x)\n'+helpers)
  for name,source in [('upstream_payload',original['ext-src/swoole_http_request.cc']),('candidate_payload',(tree/'ext-src/swoole_http_request.cc').read_text())]:
   parts=[definition(source,sig)for sig in ['static int http_request_on_body(','static int http_request_message_complete(']]
   compress=[]
   if name=='candidate_payload':compress.append(definition(source,'static uint32_t http_request_compression_capabilities('))
   compress.extend(definition(source,sig)for sig in ['void HttpContext::set_compression_method(','const char *HttpContext::get_content_encoding() const'])
   create=definition(source,'static PHP_METHOD(swoole_http_request, create) {');a=create.index('SW_HASHTABLE_FOREACH_START2(');a=create.index('{',a)+1;b=create.index('            (void) keytype;',a)
   parts.append('static void apply_option(HttpContext*ctx,const char*key,size_t keylen,zval*zvalue){\n'+create[a:b]+'\n}')
   out=tree/(name+'.cc');out.write_text('#include "payload_oracle.h"\n#include "helpers.h"\nnamespace '+name+' {\n#include "payload_wrappers.h"\n'+ '\n'.join(parts)+'\n#ifdef SW_HAVE_COMPRESSION\n'+'\n'.join(compress)+'\n#endif\n'+WRAPPERS+'\n}\n')
  binary=tree/'gate';cmd=['c++','-std=c++14','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-DPAYLOAD_CAPABILITIES='+str(args.capabilities),'-I'+str(local),'-I'+str(tree),'-I'+str(ROOT/'native/httpbindings'),str(tree/'upstream_payload.cc'),str(tree/'candidate_payload.cc'),str(local/'payload_gate.cc'),str(args.archive.resolve()),'-lm','-o',str(binary)]
  if args.native_libc:cmd=[arg for arg in cmd if not arg.startswith('-fsanitize=') and arg!='-fno-sanitize-recover=all']
  if sys.platform.startswith('linux'):cmd+=['-ldl','-lpthread','-lrt','-lutil']
  r=run_isolated(cmd,timeout=90);report['compile']={'command':cmd,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
  if not r.returncode:
   r=run_isolated([str(binary)],timeout=90,env={**os.environ,'HTTPBINDINGS_LOCALE':args.locale});report['run']={'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
   if not r.returncode:report['outcome']=json.loads(r.stdout.splitlines()[-1]);report['passed']=True
  write_report(args.output,report);print(json.dumps(report.get('outcome',report.get('run',report['compile']))));return 0 if report['passed']else 1

if __name__=='__main__':sys.exit(main())

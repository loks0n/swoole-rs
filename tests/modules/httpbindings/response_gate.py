#!/usr/bin/env python3
"""Actual Response header-tail body and known-header classifier with native effects."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from source import definition
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from tools.harness import ROOT,run_isolated,write_report
from tools.build_upstream import COMMIT as PIN
CONTEXT=r'''
struct HttpContext {
 int upgrade=0;bool keepalive=false,send_chunked=false;struct{int method=0;}parser;int send_header_=0;
 bool success=false;String buffer;String*zlib_buffer=&buffer;
 bool compress(const char*,size_t n){oracle->event("compress:"+std::to_string(n));buffer.length=17;return success;}
 const char*get_content_encoding(){oracle->event("encoding");return "gzip";}
 void build_tail(String*,const char*,size_t,uint32_t);
};
'''
WRAPPERS=r'''
Result tail(uint32_t headers,uint32_t facts,size_t length,unsigned hook,size_t fail){
 Oracle local;oracle=&local;HttpContext ctx;String output;ctx.upgrade=facts&1;ctx.keepalive=facts&2;ctx.send_chunked=facts&4;ctx.parser.method=(facts&8)?HTTP_HEAD:HTTP_POST;ctx.success=facts&32;
 local.fail=fail;
 if(hook)local.hook=[&](const std::string&event){
  if(hook==1&&event=="date"){ctx.upgrade=1;ctx.keepalive=!ctx.keepalive;}
  if(hook==2&&event.find("append:Content-Type:")==0){ctx.send_chunked=!ctx.send_chunked;ctx.parser.method=HTTP_HEAD;}
  if(hook==3&&event.find("append:Connection:")==0){ctx.upgrade=1;ctx.send_chunked=!ctx.send_chunked;ctx.keepalive=!ctx.keepalive;}
 };
 Result r;try{ctx.build_tail(&output,"body",length,headers);}catch(const Exit&){r.exited=true;}
 r.trace=local.trace;r.output=output.value;r.published=ctx.send_header_;r.facts=ctx.upgrade|(ctx.keepalive?2:0)|(ctx.send_chunked?4:0)|(ctx.parser.method==HTTP_HEAD?8:0);return r;
}
int header(const std::string&name){return http_response_parse_header_name(name.data(),name.size());}
'''

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',type=Path,required=True)
 group=parser.add_mutually_exclusive_group(required=True);group.add_argument('--archive',type=Path);group.add_argument('--rust-sanitize',action='store_true')
 parser.add_argument('--native-libc',action='store_true');parser.add_argument('--locale',default='C');parser.add_argument('--without-compression',action='store_true');parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();local=Path(__file__).resolve().parent
 report={'pin':PIN,'scope':__doc__,'limitations':'Tail after native custom header/cookie iteration, not full build_header/Zend/codec/GC/lifetime proof. Native facade assertion failures retain partial mutation and failed status; not called original PHPT passes. Native long-to-decimal helper retained; LONG_MIN-overflow input excluded.','native_sanitizers':not args.native_libc,'rust_instrumented':args.rust_sanitize,'locale':args.locale,'compression_compiled':not args.without_compression,'passed':False}
 with tempfile.TemporaryDirectory(prefix='swr-httpbindings-response-')as temp:
  tree=Path(temp)
  if args.rust_sanitize:
   args.archive=tree/'rust.a';cmd=['rustc','--edition=2024','-Zsanitizer=address','--crate-type=staticlib','-C','opt-level=3','-C','panic=abort',str(ROOT/'crates/httpbindings/src/lib.rs'),'-o',str(args.archive)]
   r=run_isolated(cmd,timeout=60,env={**os.environ,'RUSTC_BOOTSTRAP':'1'});report['rust_compile']={'command':cmd,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
   if r.returncode:write_report(args.output,report);return 1
  original={n:subprocess.check_output(['git','-C',str(args.source),'show',PIN+':'+n]).decode()for n in ['ext-src/swoole_http_response.cc','ext-src/php_swoole_http.h','include/swoole.h','src/core/base.cc']}
  for n,text in original.items():p=tree/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
  patch=ROOT/'migration/patches/httpbindings/0003-response-policy.patch'
  subprocess.run(['git','apply','--check',str(patch)],cwd=tree,check=True);subprocess.run(['git','apply',str(patch)],cwd=tree,check=True)
  enums=original['ext-src/php_swoole_http.h'];a=enums.index('enum swHttpHeaderFlag {');b=enums.index('};',a)+2
  helpers=enums[a:b]+'\nstatic constexpr int HTTP_HEAD=2,HTTP_POST=3;\n'+definition(original['include/swoole.h'],'static inline unsigned int swoole_strcaseeq(')+'\n'+definition(original['src/core/base.cc'],'int swoole_itoa(')
  for name,source in [('upstream_response',original['ext-src/swoole_http_response.cc']),('candidate_response',(tree/'ext-src/swoole_http_response.cc').read_text())]:
   body=definition(source,'void HttpContext::build_header(')
   start=body.index('    if (!(header_flags & HTTP_HEADER_SERVER)) {')if name=='upstream_response'else body.index('    uint32_t phase = 0;')
   tail='void HttpContext::build_tail(String *http_buffer,const char*body,size_t length,uint32_t header_flags){\n'+body[start:]
   parts=[definition(source,'static int http_response_parse_header_name('),definition(source,'static void http_response_set_date_header('),tail]
   p=tree/(name+'.cc');p.write_text('#include "response_oracle.h"\nnamespace '+name+' {\n'+helpers+'\n'+CONTEXT+'\n'+'\n'.join(parts)+'\n'+WRAPPERS+'\n}\n')
  binary=tree/'gate';cmd=['c++','-std=c++14','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(local),'-I'+str(ROOT/'native/httpbindings'),str(tree/'upstream_response.cc'),str(tree/'candidate_response.cc'),str(local/'response_gate.cc'),str(args.archive.resolve()),'-lm','-o',str(binary)]
  if args.native_libc:cmd=[arg for arg in cmd if not arg.startswith('-fsanitize=')and arg!='-fno-sanitize-recover=all']
  if args.without_compression:cmd.append('-DRESPONSE_NO_COMPRESSION')
  if sys.platform.startswith('linux'):cmd+=['-ldl','-lpthread','-lrt','-lutil']
  r=run_isolated(cmd,timeout=90);report['compile']={'command':cmd,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
  if not r.returncode:
   r=run_isolated([str(binary)],timeout=90,env={**os.environ,'HTTPBINDINGS_LOCALE':args.locale});report['run']={'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
   if not r.returncode:report['outcome']=json.loads(r.stdout.splitlines()[-1]);report['passed']=True
  write_report(args.output,report);print(json.dumps(report.get('outcome',report.get('run',report['compile']))));return 0 if report['passed']else 1

if __name__=='__main__':sys.exit(main())
